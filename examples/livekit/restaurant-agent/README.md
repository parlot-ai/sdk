# restaurant-agent example

Parlot-instrumented restaurant routing: greeter hands off to reservation, takeaway, or checkout specialists.

Uses LiveKit Inference for STT/LLM/TTS (no separate provider API keys required when using LiveKit Cloud inference).

Integration requirements (`configure()` + `await ctx.connect()`): see [instrumentation-livekit README](../../packages/instrumentation-livekit/README.md#integration-checklist).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and read access to the private `parlot-ai/sdk` repo (git-tag install).

```bash
cd sdk/examples/livekit/restaurant-agent
uv sync
cp .env.example .env
# edit .env
```

### SDK contributors (monorepo dev)

Replace `[tool.uv.sources]` in `pyproject.toml` with path overrides:

```toml
parlot-core = { path = "../../packages/core", editable = true }
parlot-instrumentation-livekit = { path = "../../packages/instrumentation-livekit", editable = true }
```

Then `uv sync` again.

## Run

```bash
uv run python agent.py dev
```

Agent handoffs (greeter → reservation/takeaway/checkout) appear in Parlot telemetry.
