# pipecat-minimal-voice

Minimal [Pipecat](https://github.com/pipecat-ai/pipecat) voice agent with Parlot.

Adapted from Pipecat’s official [open-telemetry/langfuse](https://github.com/pipecat-ai/pipecat-examples/tree/main/open-telemetry/langfuse) example — same STT → LLM → TTS pipeline and transport helpers, with `parlotize()` instead of Langfuse OTLP setup.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- API keys: Deepgram, Google (Gemini TTS), OpenAI
- Parlot API key (mint in **Settings → API Keys**)
- Optional: [Daily](https://daily.co) credentials if you use the Daily transport

## Run

```bash
cd examples/pipecat/minimal-voice
uv sync
cp .env.example .env
# fill PARLOT_*, DEEPGRAM_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY
uv run bot.py
```

The Pipecat runner opens a local client (WebRTC by default). Talk to the bot; the session appears in Parlot with `framework=pipecat`.

Search by the conversation UUID stamped as `platform.ref.conversation_id` (also passed as `PipelineWorker(conversation_id=…)`).

## What Parlot adds

In `bot.py`:

1. `parlotize("pipecat-minimal-voice", record=True)` before the pipeline — configures OTLP export to Parlot (do **not** also call Pipecat `setup_tracing()`).
2. `ParlotRecordingProcessor()` after `transport.output()` — mixed dual-mono stereo session audio.
3. `PipelineWorker(..., enable_tracing=True, enable_turn_tracking=True)` with metrics on.

Remove those and the bot still works — just without Parlot telemetry / recording.

## Transports

Daily, WebRTC, and WebSocket transports all work with this example. Keep a single
`parlotize` from `parlot.instrumentation.pipecat` for the process — session ownership
stays `session.agent_framework=pipecat`.

## Next

- [Pipecat guide](https://parlot.ai/docs/sdk/guides/pipecat)
- Upstream examples: [pipecat-examples](https://github.com/pipecat-ai/pipecat-examples)
