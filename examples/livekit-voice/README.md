# livekit-voice example

Demonstrates Parlot instrumentation on a standard LiveKit voice agent.

## Setup

```bash
cd sdk/examples/livekit-voice

python -m venv .venv && source .venv/bin/activate

pip install \
    "../../packages/core" \
    "../../packages/instrumentation-livekit" \
    "livekit-agents[openai,silero]"
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
python agent.py dev
```

You will see OTel spans exported to `PARLOT_ENDPOINT` after a job connects.

## What Parlot adds

At the top of `agent.py`:

```python
from parlot.instrumentation.livekit import configure, register_job_context

configure()
```

In `entrypoint`, after connecting:

```python
await ctx.connect()
await register_job_context(ctx)
```

Specifically:

- Builds a `TracerProvider` → `BatchSpanProcessor` → `OTLPSpanExporter` pointed at `PARLOT_ENDPOINT`.
- Calls `livekit.agents.telemetry.set_tracer_provider(provider)` so LiveKit emits spans.
- Registers `room_sid` / `job_id` / `room_name` for paste-search via `register_job_context`.
- Patches `AgentSession.__init__` so the agent handoff hook is installed automatically.

You can remove the Parlot calls and the agent works as before — just without telemetry.
