---
title: Pipecat
description: Instrument Pipecat voice agents with Parlot — turns, waterfall, and usage over OpenTelemetry.
sidebar_position: 3
sidebar_custom_props:
  eyebrow: Pipecat
---

# Pipecat

You already ship [Pipecat](https://docs.pipecat.ai/) voice agents. Parlot’s MIT `parlotize()`
adds a production session debugger: turns, STT/LLM/TTS waterfall, and usage — on the shared
Conversation Contract every Parlot adapter emits.

Install and env setup: [Quick Start](/sdk/get-started/quick-start). Shared product model:
[Concepts](/sdk/get-started/concepts).

## What you get in Parlot

- **Session + transcript** — turns, close reason, `framework=pipecat`
- **Pipeline waterfall** — STT / LLM / TTS timing from Pipecat’s OpenTelemetry spans
- **Usage** — tokens and character counts when `enable_metrics` / `enable_usage_metrics` are on
- **Session audio** — optional stereo capture via `ParlotRecordingProcessor` (WAV segments by default)
- **Search by conversation id** — Pipecat `conversation_id` → `platform.ref.conversation_id`

## How instrumentation works

```mermaid
flowchart LR
  PipecatOTEL["Pipecat conversation / turn / stt / llm / tts spans"] --> Remap["Parlot remap"]
  Remap --> Contract["parlot.session / parlot.turn / GenAI / voice"]
  Contract --> OTLP["OTLP to Parlot"]
```

1. Call `parlotize("…")` once at process start. This installs a TracerProvider that exports to
   Parlot and patches `PipelineWorker` so tracing + metrics default on.
2. Build your pipeline as usual. Pass `enable_tracing=True` and
   `enable_turn_tracking=True` on `PipelineWorker` (or rely on the patch).
3. Do **not** call Pipecat’s `setup_tracing()` afterward — it would replace the global
   TracerProvider and drop Parlot processors. `parlotize` is the Parlot equivalent.

Pipecat’s nested conversation→turn tree is remapped onto the Conversation Contract: one
`parlot.session` per conversation, a new OTel trace per `parlot.turn`, and service spans
renamed to the shared GenAI / voice vocabulary (`chat {model}`, `stt`, `tts`, …).

## Add it to an existing bot

```python
from parlot.instrumentation.pipecat import ParlotRecordingProcessor, parlotize

parlotize("my-pipecat-agent", version="0.1.0", record=True)

pipeline = Pipeline([
    transport.input(),
    # ... stt / llm / tts ...
    transport.output(),
    ParlotRecordingProcessor(),  # after output — mixed dual-mono stereo WAV segments
    context_aggregator.assistant(),
])

worker = PipelineWorker(
    pipeline,
    params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    enable_tracing=True,
    enable_turn_tracking=True,
    conversation_id="optional-stable-id",
)
```

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

Call `parlotize` once from `parlot.instrumentation.pipecat` for the process that owns the
pipeline. Do not mix in another framework’s `parlotize` in the same agent process.

### Recording

With `record=True` (or Settings → Recording allowlists) and `ParlotRecordingProcessor` in the
pipeline, the agent uploads ~30s stereo WAV segments via a presigned PUT, then
`POST /v1/recordings/complete`. Parlot stitches gaps as silence, normalizes for playback, and
applies close-gated PII beeps when redaction is on.

- Default deps stay thin (`wave` + `httpx`). Optional `parlot[recording-opus]` / package extra
  `recording-opus` encodes Opus/OGG segments when upstream bandwidth matters (~0.5 Mbps/call).
- Place the processor **after** `transport.output()` so both directions are buffered.
- Fail-open: upload/complete errors stamp `session.recording.status=failed` and never break the call.
- Playback is always the session’s current signed URL (redacted when policy requires) — not the
  raw segment URI.

## Example

[`examples/pipecat/minimal-voice/`](https://github.com/parlot-ai/sdk/tree/main/examples/pipecat/minimal-voice) —
adapted from Pipecat’s [open-telemetry/langfuse](https://github.com/pipecat-ai/pipecat-examples/tree/main/open-telemetry/langfuse) demo.

## Related

- [Concepts](/sdk/get-started/concepts) — Conversation Contract and shared capture policies
- [Pipecat OpenTelemetry docs](https://docs.pipecat.ai/api-reference/server/utilities/opentelemetry)
