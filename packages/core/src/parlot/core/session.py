"""Base session state accumulator shared across all instrumentation packages."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.trace import Span

_active_session_span: ContextVar[Span | None] = ContextVar(
    "_active_session_span", default=None
)
_active_session_state: ContextVar["SessionState | None"] = ContextVar(
    "_active_session_state", default=None
)


@dataclass
class SessionState:
    """
    Per-trace accumulator for cross-span aggregates.

    Framework-specific instrumentation packages subclass this to add their own
    fields (e.g. LiveKit adds agent_chain, pending_handoff_end_ns).
    """

    session_id: str = ""
    room_name: str = ""
    room_sid: str = ""
    agent_label: str = ""

    turn_count: int = 0
    tool_call_count: int = 0
    handoff_count: int = 0

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    human_rep_participant_ids: set[str] = field(default_factory=set)
    topology_agents: list[dict[str, Any]] = field(default_factory=list)
    custom_metadata: dict[str, str] = field(default_factory=dict)
