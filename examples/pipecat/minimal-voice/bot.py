#
# Adapted from Pipecat's open-telemetry/langfuse example:
# https://github.com/pipecat-ai/pipecat-examples/tree/main/open-telemetry/langfuse
#
# SPDX-License-Identifier: BSD 2-Clause License (upstream Pipecat example)
#

"""Minimal Pipecat voice bot instrumented with Parlot."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.tts import GeminiTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# ── Parlot instrumentation ────────────────────────────────────────────────
# Call after load_dotenv so PARLOT_* are available; before PipelineWorker.
from parlot.instrumentation.pipecat import ParlotRecordingProcessor, parlotize

parlotize("pipecat-minimal-voice", version="0.1.0", record=True)
# ─────────────────────────────────────────────────────────────────────────


async def get_current_weather(params: FunctionCallParams, location: str, format: str):
    """Get the current weather.

    Args:
        location: The city and state, e.g. "San Francisco, CA".
        format: The temperature unit to use. Must be either "celsius" or "fahrenheit".
    """
    await params.result_callback({"conditions": "nice", "temperature": "75"})


transport_params = {
    "daily": lambda: DailyParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport):
    logger.info("Starting bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    # Gemini TTS via GOOGLE_API_KEY (GenAI backend — pass api_key to opt in).
    tts = GeminiTTSService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GeminiTTSService.Settings(
            model="gemini-2.5-flash-preview-tts",
            voice="Kore",
            language=Language.EN_US,
        ),
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model="gpt-4o-mini",
            system_instruction=(
                "You are a helpful assistant in a voice conversation. "
                "Your responses will be spoken aloud, so avoid emojis, bullet "
                "points, or other formatting that can't be spoken. Respond "
                "briefly and helpfully."
            ),
        ),
    )

    @llm.event_handler("on_function_calls_started")
    async def on_function_calls_started(service, function_calls):
        await tts.queue_frame(TTSSpeakFrame("Let me check on that."))

    context = LLMContext(
        tools=[get_current_weather],
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    conversation_id = str(uuid.uuid4())

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            ParlotRecordingProcessor(),  # mixed dual-mono stereo → Parlot
            assistant_aggregator,
        ]
    )

    # enable_tracing / metrics are also defaulted by parlotize()'s PipelineWorker patch.
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        enable_tracing=True,
        enable_turn_tracking=True,
        conversation_id=conversation_id,
    )

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
