"""Tests for human escalation helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from parlot.core.attrs import ATTR_SESSION_TOPOLOGY_AGENTS
from parlot.core.escalation import human_escalation, record_human_rep
from parlot.core.escalation import _pending_escalation_label
from parlot.core.session import SessionState, _active_session_span, _active_session_state


def test_record_human_rep_stamps_topology_and_registers_participant() -> None:
    state = SessionState()
    span = MagicMock()
    span_token = _active_session_span.set(span)
    state_token = _active_session_state.set(state)

    try:
        record_human_rep("support_rep_jane", label="Jane")

        assert "support_rep_jane" in state.human_rep_participant_ids
        assert state.topology_agents == [
            {"id": "support_rep_jane", "role": "human_rep", "label": "Jane"}
        ]
        span.set_attribute.assert_called_once_with(
            ATTR_SESSION_TOPOLOGY_AGENTS,
            json.dumps(state.topology_agents),
        )
    finally:
        _active_session_span.reset(span_token)
        _active_session_state.reset(state_token)


def test_record_human_rep_is_idempotent_for_same_participant() -> None:
    state = SessionState()
    span = MagicMock()
    span_token = _active_session_span.set(span)
    state_token = _active_session_state.set(state)

    try:
        record_human_rep("support_rep_jane", label="Jane")
        record_human_rep("support_rep_jane", label="Jane Smith")

        assert len(state.topology_agents) == 1
        assert state.topology_agents[0]["label"] == "Jane"
    finally:
        _active_session_span.reset(span_token)
        _active_session_state.reset(state_token)


def test_human_escalation_context_manager_sets_pending_label() -> None:
    token = _pending_escalation_label.set(None)
    try:
        with human_escalation(label="Tier 2"):
            assert _pending_escalation_label.get() == "Tier 2"
        assert _pending_escalation_label.get() is None
    finally:
        _pending_escalation_label.reset(token)
