# livekit-voice example

Demonstrates Parlot instrumentation on a standard LiveKit voice agent.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd sdk/examples/livekit-voice
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

At the top of `agent.py`:

```python
from parlot.instrumentation.livekit import configure

configure()
```

In `entrypoint`:

```python
await ctx.connect()
```

Specifically:

- Builds a `TracerProvider` → `BatchSpanProcessor` → `OTLPSpanExporter` pointed at `PARLOT_ENDPOINT`.
- Calls `livekit.agents.telemetry.set_tracer_provider(provider)` so LiveKit emits spans.
- Bootstraps one `session.id` per job and stamps `room_sid` / `job_id` / `room_name` for paste-search (refreshed on connect).
- Patches `AgentSession.__init__` to install **event hooks** (turns, handoffs, usage, close) plus span enrichment for the pipeline waterfall.

You can remove the Parlot calls and the agent works as before — just without telemetry.
