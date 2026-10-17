"""
Minimal Parlot-instrumented LiveKit voice agent.

This file shows the complete integration — parlotize("…") at import. Parlot
binds the session when AgentSession reaches the listening state
(initializing→listening), not via OTEL spans.

Environment variables required:
    LIVEKIT_URL         wss://your-project.livekit.cloud
    LIVEKIT_API_KEY     your LiveKit API key
    LIVEKIT_API_SECRET  your LiveKit API secret
    PARLOT_ENDPOINT     https://ingest.parlot.ai
    PARLOT_API_KEY      your Parlot API key

Optional:
    OPENAI_API_KEY          your OpenAI API key (used by the agent below)
"""

from dotenv import load_dotenv

load_dotenv()

# ── Parlot instrumentation ────────────────────────────────────────────────
from parlot.instrumentation.livekit import parlotize

parlotize("livekit-voice")
# ─────────────────────────────────────────────────────────────────────────

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.plugins import openai, silero

server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(),
    )

    await session.start(
        room=ctx.room,
        agent=Agent(
            instructions="You are a helpful voice assistant.",
        ),
    )

    await session.generate_reply(
        instructions="Greet the user warmly and ask how you can help today."
    )


if __name__ == "__main__":
    cli.run_app(server)
