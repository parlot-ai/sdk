# livekit-voice example

Demonstrates Parlot instrumentation on a standard LiveKit voice agent.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and the [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/) (`lk`).

```bash
cd examples/livekit/livekit-voice
uv sync
cp .env.example .env.local
# edit .env.local
```

## Run

```bash
lk agent dev
```

You will see OTel spans exported to `PARLOT_ENDPOINT` after a job connects.

## What Parlot adds

See the [instrumentation-livekit integration checklist](../../packages/instrumentation-livekit/README.md#integration-checklist):

1. `configure()` at import
2. `await ctx.connect()` before `session.start()`

You can remove the Parlot calls and the agent works as before — just without telemetry.
