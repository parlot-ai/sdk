"""Tests for per-turn parlot.turn trace emission (user + agent)."""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_IS_INTERRUPTION,
    ATTR_LK_JOB_ID,
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_TURN_INDEX,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_ROLE,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor, _LiveKitSessionState


def _make_span(
    name: str,
    attributes: dict | None = None,
    start_time: int = 1_000_000_000,
    end_time: int = 2_000_000_000,
) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = start_time
    span.end_time = end_time
    span.context.trace_id = 0xDEADBEEF
    span.attributes = span._attributes
    return span


def _proc_with_exporter() -> tuple[LiveKitGenAIProcessor, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    proc = LiveKitGenAIProcessor()
    proc.set_tracer(provider.get_tracer("test"))
    return proc, exporter


def _parlot_turns(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.name == "parlot.turn"]


def _seed_state(proc: LiveKitGenAIProcessor, job_id: str = "job-1") -> _LiveKitSessionState:
    state = _LiveKitSessionState()
    state.parlot_session_id = "a" * 32
    state.conversation_id = state.parlot_session_id
    state.session_id = job_id
    proc._sessions[job_id] = state
    return state


class TestParlotTurnEmission:
    def test_eou_detection_emits_user_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(_make_span("eou_detection", {ATTR_LK_JOB_ID: "job-1"}))

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ID] == "caller"
        assert turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == "livekit_vad"

    def test_eou_interruption_skips_user_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "eou_detection",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_IS_INTERRUPTION: True},
            )
        )

        assert _parlot_turns(exporter) == []

    def test_drain_agent_activity_emits_agent_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        state = _seed_state(proc)
        state.agent_label = "Orchestrator"

        proc.on_end(
            _make_span(
                "drain_agent_activity",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_AGENT_LABEL: "Orchestrator"},
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ID] == "Orchestrator"
        assert turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == "agent_id"

    def test_llm_node_does_not_emit_parlot_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(_make_span("llm_node", {ATTR_LK_JOB_ID: "job-1"}))

        assert _parlot_turns(exporter) == []

    def test_alternating_user_agent_turn_indices(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(_make_span("eou_detection", {ATTR_LK_JOB_ID: "job-1"}))
        proc.on_end(_make_span("drain_agent_activity", {ATTR_LK_JOB_ID: "job-1"}))
        proc.on_end(_make_span("eou_detection", {ATTR_LK_JOB_ID: "job-1"}))

        turns = _parlot_turns(exporter)
        assert len(turns) == 3
        assert [t.attributes[ATTR_TURN_INDEX] for t in turns] == [1, 2, 3]
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert turns[2].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
