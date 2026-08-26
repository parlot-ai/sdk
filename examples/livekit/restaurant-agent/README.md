# restaurant-agent example

Parlot-instrumented restaurant routing: greeter hands off to reservation, takeaway, or checkout specialists.

Uses LiveKit Inference for STT/LLM/TTS (no separate provider API keys required when using LiveKit Cloud inference).

Integration requirements (`configure()` + `await ctx.connect()`): see [instrumentation-livekit README](../../packages/instrumentation-livekit/README.md#integration-checklist).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `configure(record=…)` in code.

## Setup

```bash
cd examples/livekit/restaurant-agent
uv sync
cp .env.example .env
# edit .env
```

## Run

```bash
lk agent dev
```

Agent handoffs (greeter → reservation/takeaway/checkout) appear in Parlot telemetry.
