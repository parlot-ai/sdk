"""Human escalation helpers — framework-agnostic session signals."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from parlot.core.attrs import ATTR_SESSION_TOPOLOGY_AGENTS
from parlot.core.session import _active_session_span, _active_session_state

_pending_escalation_label: ContextVar[str | None] = ContextVar(
    "_pending_escalation_label", default=None
)


def record_human_rep(participant_id: str, *, label: str | None = None) -> None:
    """
    Mark a participant as a human representative.

    Stamps ``session.topology.agents`` on the active session span and registers
    the participant for ``turn.participant_role=human_rep`` on future turns.
    """
    participant_id = str(participant_id or "").strip()
    if not participant_id:
        return

    state = _active_session_state.get()
    if state is not None:
        state.human_rep_participant_ids.add(participant_id)
        entry: dict[str, str] = {"id": participant_id, "role": "human_rep"}
        if label:
            entry["label"] = label
        if not any(a.get("id") == participant_id for a in state.topology_agents):
            state.topology_agents.append(entry)

    span = _active_session_span.get()
    if span is not None and state is not None and state.topology_agents:
        span.set_attribute(
            ATTR_SESSION_TOPOLOGY_AGENTS, json.dumps(state.topology_agents)
        )


@contextmanager
def human_escalation(label: str | None = None) -> Iterator[None]:
    """Mark the next participant who joins the active session as a human rep."""
    token = _pending_escalation_label.set(label)
    try:
        yield
    finally:
        _pending_escalation_label.reset(token)
