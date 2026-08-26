# healthcare example

Parlot-instrumented medical front-desk agent (intake, appointments, billing) based on
the [LiveKit healthcare example](https://github.com/livekit/agents/tree/main/examples/healthcare).

Keeps full upstream voice behavior (STT/LLM/TTS, AgentTasks, idle nudges) plus optional
SIP warm-transfer for human escalation on live calls. Persona sims stay in-bot and do
not require SIP.

Integration requirements (`configure()` + `await ctx.connect()`): see
[instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#integration-checklist).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `configure(record=…)` in code.

## Setup

```bash
cd examples/livekit/healthcare
uv sync
cp .env.example .env
# LIVEKIT_* for Inference; PARLOT_ENDPOINT=https://ingest.parlot.ai + PARLOT_API_KEY
```

For live warm-transfer, also set `LIVEKIT_SIP_OUTBOUND_TRUNK`,
`LIVEKIT_SUPERVISOR_PHONE_NUMBER`, and `LIVEKIT_SIP_NUMBER`.

## Interactive voice / console

```bash
uv run python agent.py console   # Ctrl+T toggles text/audio
uv run python agent.py dev       # LiveKit worker / playground
```

## Persona LLM sample sessions

Shared driver: [`../persona_sim/`](../persona_sim/).

```bash
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Returning patient books appointment"
uv run python ../persona_sim/run_persona_sim.py --all --max-turns 24
```

Each run prints `parlot_session_id=…`.
