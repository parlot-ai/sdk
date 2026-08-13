"""Drive-thru adapter for the shared persona-sim driver."""

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
    "You are the DRIVER at a fast-food drive-thru speaker, placing an order."
)


async def open_run() -> SimRun:
    import agent as drive_thru_agent  # noqa: F401 — triggers configure()

    userdata = await drive_thru_agent.new_userdata()
    return SimRun(
        agent=drive_thru_agent.DriveThruAgent(userdata=userdata),
        userdata=userdata,
        max_tool_steps=10,
        agent_speaker="Order taker",
    )
