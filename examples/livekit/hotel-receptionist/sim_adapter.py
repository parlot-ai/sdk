"""Hotel receptionist adapter for the shared persona-sim driver."""

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
    "You are the PHONE CALLER in a hotel front-desk conversation simulation."
)


async def open_run() -> SimRun:
    import agent as hotel_agent  # noqa: F401 — triggers configure()
    from common import Userdata
    from fake_data.seed import build_seed_bytes
    from hotel_db import TODAY, HotelDB

    db = HotelDB.from_bytes(build_seed_bytes(TODAY))

    async def _aclose() -> None:
        await db.aclose()

    return SimRun(
        agent=hotel_agent.HotelReceptionistAgent(),
        userdata=Userdata(db=db),
        max_tool_steps=5,
        agent_speaker="Receptionist",
        aclose=_aclose,
    )
