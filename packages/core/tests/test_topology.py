"""Unit tests for SessionTopology (framework-agnostic)."""

from parlot.core.topology import SessionTopology


def test_bootstrap_id_only() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("orchestrator", from_turn=1)
    assert topo.active_segment is not None
    assert topo.active_segment.handoff_index == 0
    assert topo.active_segment.intent_label == "Orchestrator"
    assert topo.active_segment.instructions_excerpt == ""


def test_instructions_refresh_updates_open_segment() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("orchestrator", from_turn=1)
    snap_before = topo.active_intent_snapshot()
    topo.record_instructions("orchestrator", "You are the receptionist.")
    snap_after = topo.active_intent_snapshot()
    assert snap_before[0] == "Orchestrator"
    assert "receptionist" in snap_after[0].lower()


def test_agent_reentry_three_segments() -> None:
    topo = SessionTopology()
    topo.open_bootstrap_segment("agent_a", from_turn=1)
    topo.close_active_segment(2)
    topo.open_segment_after_handoff("agent_b", handoff_index=1, turn_count=2)
    topo.close_active_segment(4)
    topo.open_segment_after_handoff("agent_a", handoff_index=2, turn_count=4)
    topo.finalize_intent_sequence(5)
    assert len(topo.intent_segments) == 3
    assert topo.intent_segments[0].agent_id == topo.intent_segments[2].agent_id == "agent_a"


def test_default_framework_on_upsert() -> None:
    topo = SessionTopology(default_framework="livekit")
    topo.upsert_agent("orchestrator")
    assert topo.agents_seen["orchestrator"].framework == "livekit"
