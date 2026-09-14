"""
Multi-agent storytelling example with Parlot instrumentation.

Based on the LiveKit agents multi_agent example: IntroAgent gathers name/location,
then hands off to StoryAgent (OpenAI Realtime) for personalized storytelling.

See packages/instrumentation-livekit/README.md for the integration checklist.
"""

import logging
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

from parlot.instrumentation.livekit import parlotize

parlotize("multi-agent")

from livekit import api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatContext,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    metrics,
)
from livekit.agents.job import get_job_context
from livekit.agents.llm import function_tool
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import deepgram, google, openai, silero

logger = logging.getLogger("multi-agent")

common_instructions = (
    "Your name is Echo. You are a story teller that interacts with the user via voice."
    "You are curious and friendly, with a sense of humor."
)


@dataclass
class StoryData:
    name: str | None = None
    location: str | None = None


class IntroAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=f"{common_instructions} Your goal is to gather a few pieces of "
            "information from the user to make the story personalized and engaging."
            "You should ask the user for their name and where they are from."
            "Start the conversation with a short introduction.",
        )

    async def on_enter(self):
        self.session.generate_reply()

    @function_tool
    async def information_gathered(
        self,
        context: RunContext[StoryData],
        name: str,
        location: str,
    ):
        """Called when the user has provided the information needed to make the story
        personalized and engaging.

        Args:
            name: The name of the user
            location: The location of the user
        """
        context.userdata.name = name
        context.userdata.location = location

        story_agent = StoryAgent(name, location)
        logger.info(
            "switching to the story agent with the provided user data: %s", context.userdata
        )
        return story_agent


class StoryAgent(Agent):
    def __init__(self, name: str, location: str, *, chat_ctx: ChatContext | None = None) -> None:
        super().__init__(
            instructions=f"{common_instructions}. You should use the user's information in "
            "order to make the story personalized."
            "create the entire story, weaving in elements of their information, and make it "
            "interactive, occasionally interating with the user."
            "do not end on a statement, where the user is not expected to respond."
            "when interrupted, ask if the user would like to continue or end."
            f"The user's name is {name}, from {location}.",
            llm=openai.realtime.RealtimeModel(voice="echo"),
            tts=None,
            chat_ctx=chat_ctx,
        )

    async def on_enter(self):
        self.session.generate_reply()

    @function_tool
    async def story_finished(self, context: RunContext[StoryData]):
        """When you are fininshed telling the story (and the user confirms they don't
        want anymore), call this function to end the conversation."""
        self.session.interrupt()

        await self.session.generate_reply(
            instructions=f"say goodbye to {context.userdata.name}", allow_interruptions=False
        )

        job_ctx = get_job_context()
        await job_ctx.api.room.delete_room(api.DeleteRoomRequest(room=job_ctx.room.name))


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    await ctx.connect()

    llm_model = google.LLM(model="gemini-3-flash-preview")

    session = AgentSession[StoryData](
        vad=ctx.proc.userdata["vad"],
        llm=llm_model,
        stt=deepgram.STT(model="nova-3"),
        tts=openai.TTS(voice="echo"),
        userdata=StoryData(),
    )

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)

    async def log_usage():
        logger.info(f"Usage: {session.usage}")

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=IntroAgent(),
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(server)
