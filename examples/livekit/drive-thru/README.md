# drive-thru example

Parlot-instrumented drive-thru ordering agent based on the
[LiveKit drive_thru example](https://github.com/livekit/agents/tree/main/examples/drive_thru).

Keeps full upstream voice behavior (STT/LLM/TTS, ambient `bg_noise.mp3`, cart RPC,
idle nudges) for playground / phone test calls. Persona sims are text-only.

Integration requirements (`configure()` + `await ctx.connect()`): see
[instrumentation-livekit README](../../../packages/instrumentation-livekit/README.md#integration-checklist).

Recording follows Parlot **Settings → Recording** (telemetry bootstrap). Override per job with `{ "record": true|false }` in dispatch metadata or `configure(record=…)` in code.

## Setup

```bash
cd examples/livekit/drive-thru
uv sync
cp .env.example .env
# LIVEKIT_* for Inference; PARLOT_ENDPOINT=https://ingest.parlot.ai + PARLOT_API_KEY
```

## Interactive voice / console

```bash
uv run python agent.py console   # Ctrl+T toggles text/audio
uv run python agent.py dev       # LiveKit worker / playground
```

## Persona LLM sample sessions

Shared driver: [`../persona_sim/`](../persona_sim/).

```bash
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Simple Big Mac combo order"
uv run python ../persona_sim/run_persona_sim.py --all --max-turns 20
```

Each run prints `parlot_session_id=…`.
