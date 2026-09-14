"""Tests for SessionTopology."""

from __future__ import annotations

import json

from parlot.core.attrs import (
    ATTR_SESSION_AGENT_CHAIN,
    ATTR_SESSION_AGENT_CHAIN_TRUNCATED,
    ATTR_SESSION_INTENT_SEQUENCE,
    ATTR_SESSION_INTENT_SEQUENCE_TRUNCATED,
)
from parlot.core.topology import (
    MAX_AGENT_CHAIN_STEPS,
    MAX_INTENT_SEGMENTS,
    MAX_JSON_CHARS,
    SessionTopology,
    _json_dumps_cap,
)


class _Span:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


def test_topology_records_instructions_on_segments() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("greeter", 1)
    topo.record_instructions("greeter", "You are a friendly restaurant receptionist.")
    topo.apply_pending_from_turn_on_emit(1)
    topo.open_segment_after_handoff(
        "takeaway",
        turn_index=3,
        from_agent="greeter",
    )
    topo.record_instructions("takeaway", "You are a takeaway agent.")
    topo.apply_pending_from_turn_on_emit(4)
    topo.close_active_segment(10)

    sequence = topo.finalize_intent_sequence(10)
    assert len(sequence) == 2
    assert sequence[0]["agent_id"] == "greeter"
    assert "restaurant receptionist" in sequence[0]["instructions_excerpt"]
    assert sequence[1]["agent_id"] == "takeaway"
    assert "takeaway agent" in sequence[1]["instructions_excerpt"]


def test_topology_dedupes_duplicate_handoffs() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("greeter", 1)
    topo.open_segment_after_handoff("takeaway", turn_index=3, from_agent="greeter")
    topo.open_segment_after_handoff("takeaway", turn_index=3, from_agent="greeter")
    topo.close_active_segment(5)
    assert len(topo.finalize_intent_sequence(5)) == 2


def test_handoff_keys_cleared_across_turns() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("greeter", 1)
    topo.open_segment_after_handoff("takeaway", turn_index=3, from_agent="greeter")
    assert len(topo._handoff_keys) == 1
    topo.open_segment_after_handoff("greeter", turn_index=4, from_agent="takeaway")
    assert topo._handoff_keys_turn == 4
    assert len(topo._handoff_keys) == 1
    # Same routing on a new turn is not suppressed.
    topo.open_segment_after_handoff("takeaway", turn_index=5, from_agent="greeter")
    assert len(topo._handoff_keys) == 1
    assert "greeter->takeaway@5" in topo._handoff_keys


def test_agent_chain_step_cap_keeps_first_and_recent() -> None:
    topo = SessionTopology()
    topo.push_agent_chain("canonical")
    for i in range(MAX_AGENT_CHAIN_STEPS + 20):
        topo.push_agent_chain(f"step-{i}")
    assert len(topo.agent_chain) == MAX_AGENT_CHAIN_STEPS
    assert topo.agent_chain[0] == "canonical"
    assert topo.agent_chain[-1] == f"step-{MAX_AGENT_CHAIN_STEPS + 19}"


def test_agent_chain_char_cap_independent_of_step_cap() -> None:
    topo = SessionTopology()
    long_id = "a" * (MAX_JSON_CHARS // 2)
    topo.push_agent_chain(long_id)
    topo.push_agent_chain(long_id + "b")
    assert len(topo.agent_chain) == 2
    span = _Span()
    topo.stamp_session_span(span, final_turn=1)
    chain_attr = span.attributes[ATTR_SESSION_AGENT_CHAIN]
    assert isinstance(chain_attr, str)
    assert len(chain_attr) <= MAX_JSON_CHARS
    assert span.attributes.get(ATTR_SESSION_AGENT_CHAIN_TRUNCATED) is True


def test_chain_and_segments_windows_may_diverge() -> None:
    """MAX_AGENT_CHAIN_STEPS and MAX_INTENT_SEGMENTS are independent retention windows."""
    assert MAX_AGENT_CHAIN_STEPS != MAX_INTENT_SEGMENTS
    topo = SessionTopology()
    topo.push_agent_chain("seed")
    topo.open_bootstrap_segment("a", 1)
    # Ping-pong past both caps; chain window is smaller than segment window.
    steps = max(MAX_AGENT_CHAIN_STEPS, MAX_INTENT_SEGMENTS) + 10
    for i in range(steps):
        agent = "a" if i % 2 == 0 else "b"
        other = "b" if agent == "a" else "a"
        topo.push_agent_chain(agent)
        topo.open_segment_after_handoff(agent, turn_index=i + 1, from_agent=other)
    assert len(topo.agent_chain) == MAX_AGENT_CHAIN_STEPS
    assert len(topo.intent_segments) == MAX_INTENT_SEGMENTS
    # Still-open active segment is not part of the closed trim.
    assert topo.active_segment is not None
    sequence = topo.finalize_intent_sequence(steps + 1)
    assert len(sequence) == MAX_INTENT_SEGMENTS
    # Stamped chain step count and intent sequence length are allowed to diverge.
    assert len(topo.agent_chain) != len(sequence)


def test_consecutive_same_agent_merges_on_close() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("greeter", 1)
    topo.close_active_segment(2)
    topo.active_segment = topo._new_segment("greeter", 3, 1)
    topo.close_active_segment(5)
    assert len(topo.intent_segments) == 1
    assert topo.intent_segments[0].to_turn == 5
    sequence = topo.finalize_intent_sequence(5)
    assert len(sequence) == 1
    assert sequence[0]["agent_id"] == "greeter"
    assert sequence[0]["to_turn"] == 5


def test_trim_closed_segments_leaves_active_untouched() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("a", 1)
    for i in range(MAX_INTENT_SEGMENTS + 5):
        agent = "a" if i % 2 == 0 else "b"
        other = "b" if agent == "a" else "a"
        topo.open_segment_after_handoff(agent, turn_index=i + 1, from_agent=other)
    assert len(topo.intent_segments) == MAX_INTENT_SEGMENTS
    active = topo.active_segment
    assert active is not None
    topo._trim_closed_segments()
    assert topo.active_segment is active
    assert len(topo.intent_segments) == MAX_INTENT_SEGMENTS


def test_json_dumps_cap_keeps_recent_and_reports_truncation() -> None:
    items = [{"agent_id": f"agent-{i}", "blob": "x" * 2000} for i in range(50)]
    raw, truncated = _json_dumps_cap(items)
    assert truncated is True
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert parsed
    assert all("agent_id" in item for item in parsed)
    assert parsed[-1]["agent_id"] == "agent-49"
    assert "truncated" not in parsed[0]


def test_stamp_sets_intent_sequence_truncated_attr(monkeypatch) -> None:
    import parlot.core.topology as topology_mod

    monkeypatch.setattr(topology_mod, "MAX_JSON_CHARS", 200)
    topo = SessionTopology()
    topo.open_bootstrap_segment("greeter", 1)
    topo.record_instructions("greeter", "You are a greeter. " * 20)
    for i in range(8):
        agent = "takeaway" if i % 2 == 0 else "greeter"
        other = "greeter" if agent == "takeaway" else "takeaway"
        topo.open_segment_after_handoff(agent, turn_index=i + 2, from_agent=other)
        topo.record_instructions(agent, f"You are {agent}. " * 20)
    span = _Span()
    topo.stamp_session_span(span, final_turn=20)
    assert ATTR_SESSION_INTENT_SEQUENCE in span.attributes
    seq = json.loads(str(span.attributes[ATTR_SESSION_INTENT_SEQUENCE]))
    assert isinstance(seq, list)
    assert all("agent_id" in item for item in seq)
    assert span.attributes.get(ATTR_SESSION_INTENT_SEQUENCE_TRUNCATED) is True
