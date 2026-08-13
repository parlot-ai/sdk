"""Contract for example-specific persona-sim adapters.

Each LiveKit example that supports automated text sessions exposes a
``sim_adapter`` module implementing :class:`PersonaSimAdapter`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from livekit.agents import Agent


@dataclass
class SimRun:
    """One persona-sim session setup owned by an example adapter."""

    agent: Agent
    userdata: Any = None
    max_tool_steps: int = 5
    #: Spoken label used when feeding agent replies back to the persona LLM.
    agent_speaker: str = "Agent"
    aclose: Callable[[], Awaitable[None]] | None = field(default=None)


class PersonaSimAdapter(Protocol):
    """Loaded from ``<example>/sim_adapter.py`` (cwd on sys.path)."""

    DEFAULT_SCENARIOS: Path
    #: Role blurb only; shared driver appends universal caller rules + hangup.
    PERSONA_ROLE: str

    async def open_run(self) -> SimRun: ...
