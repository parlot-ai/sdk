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
    # Owning instrumentation package, e.g. "livekit" | "langgraph"
    framework: str = ""


def get_active_session() -> SessionState | None:
    """Return the session state bound to the current context, if any."""
    return _active_session_state.get()


def get_active_session_span() -> Span | None:
    """Return the active ``parlot.session`` span for the current context, if any."""
    return _active_session_span.get()


def set_active_session(
    span: Span | None,
    state: SessionState | None,
) -> None:
    """Bind (or clear) the active session span + state for this context."""
    _active_session_span.set(span)
    _active_session_state.set(state)


def clear_active_session() -> None:
    """Clear the active session bindings for this context."""
    set_active_session(None, None)


def session_owned(*, framework: str | None = None) -> bool:
    """True when an active Parlot session with a non-empty session_id is bound.

    Args:
        framework: If provided, also require ``state.framework`` to match
            (e.g. ``session_owned(framework="livekit")`` for coexistence checks).
    """
    state = get_active_session()
    if state is None or not state.session_id:
        return False
    if framework is not None and state.framework != framework:
        return False
    return True
