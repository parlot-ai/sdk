# livekit-voice example

Demonstrates zero-config Parlot instrumentation on a standard LiveKit voice agent.

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

You will see OTel spans exported to `PARLOT_ENDPOINT` immediately. No boilerplate required.

## What Parlot adds

The two lines at the top of `agent.py` do everything:

```python
from parlot.instrumentation.livekit import configure
configure()
```

Specifically:
- Builds a `TracerProvider` → `BatchSpanProcessor` → `OTLPSpanExporter` pointed at `PARLOT_ENDPOINT`.
- Calls `livekit.agents.telemetry.set_tracer_provider(provider)` so LiveKit emits spans.
- Patches `WorkerOptions.__init__` so job context (room SID, job ID) is registered automatically.
- Patches `AgentSession.__init__` so the agent handoff hook is installed automatically.

You can remove both lines and the agent works exactly as before — just without telemetry.
