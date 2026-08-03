# livekit-voice example

Demonstrates Parlot instrumentation on a standard LiveKit voice agent.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd sdk/examples/livekit/livekit-voice
uv sync
```

## Configure

Copy `.env.example` and fill in your credentials:

```bash
cp .env.example .env
# edit .env
source .env
```

## Run

```bash
uv run python agent.py dev
```

You will see OTel spans exported to `PARLOT_ENDPOINT` after a job connects.

## What Parlot adds

See the [instrumentation-livekit integration checklist](../../packages/instrumentation-livekit/README.md#integration-checklist):

1. `configure()` at import
2. `await ctx.connect()` before `session.start()`

You can remove the Parlot calls and the agent works as before — just without telemetry.
