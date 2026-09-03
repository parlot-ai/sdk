"""Tests for per-turn parlot.turn trace emission (user + agent)."""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanContext, TraceFlags

from parlot.core.attrs import (
    ATTR_DIAR_SOURCE_AGENT_ID,
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_SESSION_ID,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_LANGUAGE,
    ATTR_TURN_LANGUAGE_SWITCH,
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_SPEECH_WALL_END_MS,
    ATTR_TURN_SPEECH_WALL_START_MS,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_IS_INTERRUPTION,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_LK_USER_TRANSCRIPT,
    ATTR_DIAR_SOURCE_TEXT_INPUT,
    ATTR_DIAR_SOURCE_VAD,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session_state import _LiveKitSessionState
from parlot.instrumentation.livekit._turn_trace_export import TurnTraceRemappingExporter
from bootstrap_helpers import bootstrap_via_agent_state


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
    proc = LiveKitGenAIProcessor()
    provider.add_span_processor(proc)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    proc.set_tracer(provider.get_tracer("test"))
    return proc, exporter


def _bootstrap_job(proc: LiveKitGenAIProcessor, job_id: str = "job-1") -> None:
    bootstrap_via_agent_state(proc, job_id)


def _parlot_turns(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.name == "parlot.turn"]


def _seed_state(proc: LiveKitGenAIProcessor, job_id: str = "job-1") -> _LiveKitSessionState:
    _bootstrap_job(proc, job_id)
    from parlot.instrumentation.livekit._session import get_job_bootstrap

    return get_job_bootstrap().state


class TestParlotTurnEmission:
    def test_user_turn_emits_user_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_USER_TRANSCRIPT: "I want an appointment",
                },
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ID] == "caller"
        assert turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == ATTR_DIAR_SOURCE_VAD
        assert turns[0].attributes[ATTR_TURN_INPUT_MODALITY] == "voice"

    def test_user_turn_interruption_skips_emission(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_IS_INTERRUPTION: True,
                    ATTR_LK_USER_TRANSCRIPT: "hello",
                },
            )
        )

        assert _parlot_turns(exporter) == []

    def test_agent_turn_emits_agent_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        state = _seed_state(proc)
        state.agent_label = "Orchestrator"
        state.open_agent_turn_index = 2

        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_AGENT_LABEL: "Orchestrator"},
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ID] == "Orchestrator"
        assert turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == ATTR_DIAR_SOURCE_AGENT_ID

    def test_agent_turn_synthesizes_user_turn_without_user_turn_span(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "agent_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_AGENT_LABEL: "Orchestrator",
                    ATTR_LK_USER_INPUT: "friday 2pm",
                },
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 2
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ID] == "caller"
        assert turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == ATTR_DIAR_SOURCE_TEXT_INPUT
        assert turns[0].attributes[ATTR_TURN_INPUT_MODALITY] == "text"
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert [t.attributes[ATTR_TURN_INDEX] for t in turns] == [1, 2]

    def test_user_turn_text_only_modality(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_USER_INPUT: "friday 2pm"},
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_INPUT_MODALITY] == "text"
        assert turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == ATTR_DIAR_SOURCE_TEXT_INPUT

    def test_llm_node_does_not_emit_parlot_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(_make_span("llm_node", {ATTR_LK_JOB_ID: "job-1"}))

        assert _parlot_turns(exporter) == []

    def test_alternating_user_agent_turn_indices(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_USER_TRANSCRIPT: "hi"},
            )
        )
        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_AGENT_LABEL: "Orchestrator"},
            )
        )
        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_USER_TRANSCRIPT: "book"},
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 3
        assert [t.attributes[ATTR_TURN_INDEX] for t in turns] == [1, 2, 3]
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert turns[2].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"

    def test_agent_pipeline_turn_index_matches_agent_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_USER_TRANSCRIPT: "hello"},
            )
        )

        llm = _make_span("llm_node", {ATTR_LK_JOB_ID: "job-1"})
        proc.on_end(llm)
        assert llm._attributes[ATTR_TURN_INDEX] == 2

        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_AGENT_LABEL: "Orchestrator"},
            )
        )

        turns = _parlot_turns(exporter)
        assert [t.attributes[ATTR_TURN_INDEX] for t in turns] == [1, 2]

    def test_agent_label_from_start_agent_activity(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        proc.on_end(
            _make_span(
                "start_agent_activity",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_AGENT_LABEL: "get_email_task"},
            )
        )
        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_USER_TRANSCRIPT: "email?"},
            )
        )
        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_JOB_ID: "job-1"},
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 2
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ID] == "get_email_task"

    def test_export_remaps_child_trace_id(self) -> None:
        proc, _exporter = _proc_with_exporter()
        state = _seed_state(proc)

        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_USER_TRANSCRIPT: "hi"},
            )
        )
        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_JOB_ID: "job-1", ATTR_LK_AGENT_LABEL: "agent"},
            )
        )

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

    def test_user_turn_copies_speech_wall_and_otlp_duration(self) -> None:
        proc, exporter = _proc_with_exporter()
        _seed_state(proc)

        speech_start = 1_700_000_000_000_000_000
        speech_end = speech_start + 1_000_000_000

        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_USER_TRANSCRIPT: "hello",
                },
                start_time=speech_start,
                end_time=speech_end,
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        attrs = turns[0].attributes
        assert attrs[ATTR_TURN_SPEECH_WALL_START_MS] == speech_start // 1_000_000
        assert attrs[ATTR_TURN_SPEECH_WALL_END_MS] == speech_end // 1_000_000
        assert attrs.get(ATTR_TURN_MEDIA_START_MS, 0) == 0
        assert attrs.get(ATTR_TURN_MEDIA_END_MS, 0) == 0
        assert turns[0].end_time - turns[0].start_time == speech_end - speech_start

    def test_recording_anchor_sets_media_segments(self) -> None:
        proc, exporter = _proc_with_exporter()
        state = _seed_state(proc)

        anchor_ms = 1_700_000_000_000
        proc.set_recording_anchor_wall_ms(state, anchor_ms)

        speech_start = (anchor_ms + 500) * 1_000_000
        speech_end = (anchor_ms + 2500) * 1_000_000

        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_USER_TRANSCRIPT: "book",
                },
                start_time=speech_start,
                end_time=speech_end,
            )
        )

        turns = _parlot_turns(exporter)
        assert turns[0].attributes[ATTR_TURN_MEDIA_START_MS] == 500
        assert turns[0].attributes[ATTR_TURN_MEDIA_END_MS] == 2500

    def test_agent_turn_language_and_switch(self) -> None:
        proc, exporter = _proc_with_exporter()
        state = _seed_state(proc)
        state.last_agent_turn_language = "en"
        state.open_agent_turn_index = 2

        proc.on_end(
            _make_span(
                "agent_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_AGENT_LABEL: "Orchestrator",
                    ATTR_LK_RESPONSE_TEXT: "Claro, puedo ayudarte con eso",
                },
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_LANGUAGE] == "es"
        assert turns[0].attributes[ATTR_TURN_LANGUAGE_SWITCH] == '{"from": "en", "to": "es"}'

    def test_agent_turn_without_metrics_leaves_media_unset(self) -> None:
        """Long agent_turn bounds must not become media_segment_* (AgentTasks)."""
        proc, exporter = _proc_with_exporter()
        state = _seed_state(proc)
        anchor_ms = 1_700_000_000_000
        proc.set_recording_anchor_wall_ms(state, anchor_ms)
        state.open_agent_turn_index = 24

        # Span starts near session begin but ends much later (tool / AgentTask).
        speech_start = (anchor_ms + 3_000) * 1_000_000
        speech_end = (anchor_ms + 160_000) * 1_000_000

        proc.on_end(
            _make_span(
                "agent_turn",
                {
                    ATTR_LK_JOB_ID: "job-1",
                    ATTR_LK_AGENT_LABEL: "Orchestrator",
                    ATTR_LK_RESPONSE_TEXT: "I'll transfer you now",
                },
                start_time=speech_start,
                end_time=speech_end,
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        attrs = turns[0].attributes
        assert attrs.get(ATTR_TURN_MEDIA_START_MS, 0) in (0, None)
        assert attrs.get(ATTR_TURN_SPEECH_WALL_START_MS, 0) in (0, None)

    def test_recording_anchor_freezes_after_first_set(self) -> None:
        proc, _exporter = _proc_with_exporter()
        state = _seed_state(proc)
        proc.set_recording_anchor_wall_ms(state, 1_000_000)
        proc.set_recording_anchor_wall_ms(state, 9_999_999)
        assert state.recording_anchor_wall_ms == 1_000_000

    def test_events_mode_stamps_turn_index_on_agent_turn(self) -> None:
        proc, _exporter = _proc_with_exporter()
        state = _seed_state(proc)
        proc.set_turn_source("events")
        state.open_agent_turn_index = 5
        span = _make_span(
            "agent_turn",
            {
                ATTR_LK_JOB_ID: "job-1",
                ATTR_LK_RESPONSE_TEXT: "hi",
            },
        )
        proc.on_end(span)
        assert span._attributes[ATTR_TURN_INDEX] == 5

    def test_merge_requires_turn_index_and_skips_agent_span_media(self) -> None:
        from parlot.core.attrs import ATTR_TURN_E2E_LATENCY_S
        from parlot.instrumentation.livekit.attrs import ATTR_LK_E2E_LATENCY

        proc, _exporter = _proc_with_exporter()
        state = _seed_state(proc)
        state.turn_count = 24
        state.pending_turn_pipeline_attrs.clear()
        anchor_ms = 1_700_000_000_000
        proc.set_recording_anchor_wall_ms(state, anchor_ms)

        native_no_index = _make_span(
            "agent_turn",
            {
                ATTR_LK_JOB_ID: "job-1",
                ATTR_LK_E2E_LATENCY: 1.5,
                ATTR_LK_RESPONSE_TEXT: "hello",
            },
            start_time=(anchor_ms + 3_000) * 1_000_000,
            end_time=(anchor_ms + 10_000) * 1_000_000,
        )
        proc._turns.merge_native_turn_attrs_onto_parlot_turns([native_no_index])
        assert state.pending_turn_pipeline_attrs == {}

        native_with_index = _make_span(
            "agent_turn",
            {
                ATTR_LK_JOB_ID: "job-1",
                ATTR_LK_E2E_LATENCY: 1.5,
                ATTR_LK_RESPONSE_TEXT: "hello",
                ATTR_TURN_INDEX: 24,
            },
            start_time=(anchor_ms + 3_000) * 1_000_000,
            end_time=(anchor_ms + 10_000) * 1_000_000,
        )
        proc._turns.merge_native_turn_attrs_onto_parlot_turns([native_with_index])
        pending = state.pending_turn_pipeline_attrs.get(24, {})
        assert pending.get(ATTR_TURN_E2E_LATENCY_S) == 1.5
        assert ATTR_TURN_MEDIA_START_MS not in pending
        assert ATTR_TURN_SPEECH_WALL_START_MS not in pending
