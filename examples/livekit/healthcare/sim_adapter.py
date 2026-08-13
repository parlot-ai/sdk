"""Healthcare adapter for the shared persona-sim driver."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PERSONA_SIM = _ROOT.parent / "persona_sim"
if str(_PERSONA_SIM) not in sys.path:
    sys.path.insert(0, str(_PERSONA_SIM))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from adapter import SimRun  # noqa: E402

DEFAULT_SCENARIOS = _ROOT / "sim_scenarios.yaml"
PERSONA_ROLE = (
    "You are the PHONE CALLER speaking with a medical front-desk assistant."
)


async def open_run() -> SimRun:
    import agent as healthcare_agent  # noqa: F401 — triggers configure()
    from fake_database import FakeDatabase

    db = FakeDatabase()
    userdata = healthcare_agent.UserData(database=db, profile=None)
    return SimRun(
        agent=healthcare_agent.HealthcareAgent(database=db),
        userdata=userdata,
        max_tool_steps=8,
        agent_speaker="Front desk",
    )
