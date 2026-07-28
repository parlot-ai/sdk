"""Tests for SessionTopology."""

from parlot.core.topology import SessionTopology


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
