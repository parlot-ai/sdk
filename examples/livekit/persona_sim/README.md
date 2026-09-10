# Shared persona-LLM session driver for LiveKit examples.

Each example that supports automated text sims provides:

- `sim_adapter.py` — builds the agent + userdata (`open_run`)
- `sim_scenarios.yaml` — PERSONA / OPENING LINE / FACTS / DO scenarios

## Run from an example directory

```bash
cd examples/livekit/hotel-receptionist
uv sync
uv run python ../persona_sim/run_persona_sim.py --list
uv run python ../persona_sim/run_persona_sim.py --label "Simple room booking by phone"
uv run python ../persona_sim/run_persona_sim.py --all --max-turns 24
```

`uv run` uses the example's environment (Parlot path deps, LiveKit Inference).
The driver loads `.env` from the example cwd.

## Adapter contract

See [`adapter.py`](adapter.py). Minimum `sim_adapter.py`:

```python
from pathlib import Path
from persona_sim.adapter import SimRun  # or import via sys.path

DEFAULT_SCENARIOS = Path(__file__).parent / "sim_scenarios.yaml"
PERSONA_ROLE = "You are the PHONE CALLER in a … conversation simulation."

async def open_run() -> SimRun:
    import agent  # triggers parlotize()
    return SimRun(agent=agent.MyAgent(), userdata=..., agent_speaker="Receptionist")
```

When adding a new example, copy an existing `sim_adapter.py` and swap agent/userdata construction.
