"""Tests for per-turn parlot.turn trace emission (user + agent)."""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanContext, TraceFlags

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
from parlot.instrumentation.livekit._turn_trace_export import TurnTraceRemappingExporter


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

    def test_agent_pipeline_turn_index_matches_agent_turn(self) -> None:
        """After user EOU, llm_node stamps open_agent_turn_index (not stale turn_count)."""
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(_make_span("eou_detection", {ATTR_LK_JOB_ID: "job-1"}))

        llm = _make_span("llm_node", {ATTR_LK_JOB_ID: "job-1"})
        proc.on_end(llm)
        assert llm._attributes[ATTR_TURN_INDEX] == 2

        drain = _make_span("drain_agent_activity", {ATTR_LK_JOB_ID: "job-1"})
        proc.on_end(drain)
        assert drain._attributes[ATTR_TURN_INDEX] == 2

        turns = _parlot_turns(exporter)
        assert [t.attributes[ATTR_TURN_INDEX] for t in turns] == [1, 2]

    def test_export_remaps_child_trace_id(self) -> None:
        proc, _exporter = _proc_with_exporter()
        state = _seed_state(proc)

        proc.on_end(_make_span("eou_detection", {ATTR_LK_JOB_ID: "job-1"}))
        proc.on_end(_make_span("drain_agent_activity", {ATTR_LK_JOB_ID: "job-1"}))

        from parlot.core.attrs import ATTR_SESSION_ID

        session_id = state.parlot_session_id
        job_trace = 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        llm_ctx = SpanContext(
            trace_id=job_trace,
            span_id=0xBBBBBBBBBBBBBBBB,
            is_remote=False,
            trace_flags=TraceFlags(0x01),
        )
        llm = _make_span(
            "llm_node",
            {
                ATTR_LK_JOB_ID: "job-1",
                ATTR_SESSION_ID: session_id,
                ATTR_TURN_INDEX: 2,
            },
        )
        llm.context = llm_ctx
        llm.get_span_context = MagicMock(return_value=llm_ctx)
        llm.parent = None

        captured: list = []

        class _Cap:
            def export(self, spans):
                captured.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self):
                pass

            def force_flush(self, timeout_millis=30000):
                return True

        remapper = TurnTraceRemappingExporter(_Cap(), proc)
        remapper.export([llm])

        assert len(captured) == 1
        turn_trace_hex, _ = proc.lookup_turn_trace(session_id, 2)
        assert turn_trace_hex is not None
        assert captured[0].get_span_context().trace_id == int(turn_trace_hex, 16)
