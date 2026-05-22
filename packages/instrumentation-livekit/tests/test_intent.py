"""Intent segment sequence (bootstrap, handoff, refresh vs turn snapshots)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_SESSION_INTENT_SEQUENCE,
    ATTR_TURN_ACTIVE_AGENT_ID,
    ATTR_TURN_INTENT_KEY,
    ATTR_TURN_INTENT_LABEL,
    ATTR_TURN_PARTICIPANT_ROLE,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_JOB_ID,
    ATTR_LK_USER_TRANSCRIPT,
)
from parlot.core.intent import derive_intent
from parlot.core.topology import SessionTopology
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import get_job_bootstrap


def _make_span(name: str, attributes: dict | None = None) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
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


def _parlot_turns(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.name == "parlot.turn"]


class TestDeriveIntent:
    def test_id_only_when_no_instructions(self) -> None:
        key, label, excerpt = derive_intent("cancel_task", "")
        assert key == "cancel_task"
        assert label == "Cancel Task"
        assert excerpt == ""

    def test_first_line_label_with_instructions(self) -> None:
        key, label, excerpt = derive_intent(
            "book_appointment",
            "Book appointments for callers.\nMore detail here.",
        )
        assert key == "book_appointment"
        assert label == "Book appointments for callers."
        assert "More detail" in excerpt


class TestIntentSegmentTopology:
    def test_bootstrap_id_only(self) -> None:
        topo = SessionTopology()
        topo.open_bootstrap_segment("orchestrator", from_turn=1)
        assert topo.active_segment is not None
        assert topo.active_segment.handoff_index == 0
        assert topo.active_segment.intent_label == "Orchestrator"
        assert topo.active_segment.instructions_excerpt == ""

    def test_instructions_refresh_updates_segment_not_prior_turns(self) -> None:
        topo = SessionTopology()
        topo.open_bootstrap_segment("orchestrator", from_turn=1)
        snap_before = topo.active_intent_snapshot()
        topo.record_instructions("orchestrator", "You are the receptionist.")
        snap_after = topo.active_intent_snapshot()
        assert snap_before[0] == "Orchestrator"
        assert "receptionist" in snap_after[0].lower()
        assert topo.active_segment is not None
        assert "receptionist" in topo.active_segment.intent_label.lower()

    def test_handoff_from_turn_matches_next_emitted(self) -> None:
        topo = SessionTopology()
        topo.open_bootstrap_segment("agent_a", from_turn=1)
        topo.close_active_segment(1)
        topo.open_segment_after_handoff("agent_b", handoff_index=1, turn_count=1)
        assert topo.pending_segment_from_turn == 2
        topo.apply_pending_from_turn_on_emit(2)
        assert topo.active_segment is not None
        assert topo.active_segment.from_turn == 2
        assert topo.active_segment.handoff_index == 1

    def test_agent_reentry_two_segments(self) -> None:
        topo = SessionTopology()
        topo.open_bootstrap_segment("agent_a", from_turn=1)
        topo.close_active_segment(2)
        topo.open_segment_after_handoff("agent_b", handoff_index=1, turn_count=2)
        topo.close_active_segment(4)
        topo.open_segment_after_handoff("agent_a", handoff_index=2, turn_count=4)
        topo.finalize_intent_sequence(5)
        assert len(topo.intent_segments) == 3
        assert topo.intent_segments[0].agent_id == "agent_a"
        assert topo.intent_segments[2].agent_id == "agent_a"
        assert topo.intent_segments[1].agent_id == "agent_b"


class TestIntentProcessorIntegration:
    def test_intent_segment_bootstrap_id_only(self) -> None:
        proc, exporter = _proc_with_exporter()
        entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "job-intent-1"})
        proc.on_start(entry)
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-1",
                    ATTR_LK_AGENT_LABEL: "orchestrator",
                    ATTR_LK_USER_TRANSCRIPT: "hello",
                },
            )
        )
        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_INTENT_LABEL] == "Orchestrator"
        assert turns[0].attributes[ATTR_TURN_INTENT_KEY] == "orchestrator"

    def test_session_close_before_instructions(self) -> None:
        proc, _exporter = _proc_with_exporter()
        entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "job-intent-2"})
        proc.on_start(entry)
        session_span = get_job_bootstrap().session_span
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-2",
                    ATTR_LK_AGENT_LABEL: "task_agent",
                    ATTR_LK_USER_TRANSCRIPT: "hi",
                },
            )
        )
        proc.on_end(entry)
        raw = session_span._attributes.get(ATTR_SESSION_INTENT_SEQUENCE)
        assert raw
        segments = json.loads(str(raw))
        assert len(segments) == 1
        assert segments[0]["agent_id"] == "task_agent"
        assert segments[0]["handoff_index"] == 0
        assert "instructions_excerpt" not in segments[0]

    def test_instructions_refresh_updates_segment_not_prior_turns(self) -> None:
        proc, exporter = _proc_with_exporter()
        entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "job-intent-3"})
        proc.on_start(entry)
        session_span = get_job_bootstrap().session_span
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-3",
                    ATTR_LK_AGENT_LABEL: "orchestrator",
                    ATTR_LK_USER_TRANSCRIPT: "first",
                },
            )
        )
        turns_early = _parlot_turns(exporter)
        assert turns_early[0].attributes[ATTR_TURN_INTENT_LABEL] == "Orchestrator"

        chat_ctx = json.dumps(
            [
                {
                    "type": "agent_config_update",
                    "instructions": "You are the appointment orchestrator.",
                }
            ]
        )
        proc.on_end(
            _make_span(
                "llm_node",
                {
                    ATTR_LK_JOB_ID: "job-intent-3",
                    ATTR_LK_AGENT_LABEL: "orchestrator",
                    ATTR_LK_CHAT_CTX: chat_ctx,
                },
            )
        )
        proc.on_end(entry)
        segments = json.loads(
            str(session_span._attributes[ATTR_SESSION_INTENT_SEQUENCE])
        )
        assert "orchestrator" in segments[-1]["intent_label"].lower()
        assert turns_early[0].attributes[ATTR_TURN_INTENT_LABEL] == "Orchestrator"

    def test_handoff_from_turn_matches_next_emitted_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "job-intent-4"})
        proc.on_start(entry)
        session_span = get_job_bootstrap().session_span
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-4",
                    ATTR_LK_AGENT_LABEL: "agent_a",
                    ATTR_LK_USER_TRANSCRIPT: "one",
                },
            )
        )
        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_JOB_ID: "job-intent-4", ATTR_LK_AGENT_LABEL: "agent_a"},
            )
        )
        proc.on_end(
            _make_span(
                "lk.agent_handoff",
                {
                    ATTR_LK_JOB_ID: "job-intent-4",
                    ATTR_AGENT_TRANSFER_FROM: "agent_a",
                    ATTR_AGENT_TRANSFER_TO: "agent_b",
                },
            )
        )
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-4",
                    ATTR_LK_AGENT_LABEL: "agent_b",
                    ATTR_LK_USER_TRANSCRIPT: "two",
                },
            )
        )
        turns = _parlot_turns(exporter)
        assert len(turns) >= 3
        last_user = [
            t for t in turns if t.attributes.get(ATTR_TURN_PARTICIPANT_ROLE) == "user"
        ][-1]
        assert last_user.attributes[ATTR_TURN_ACTIVE_AGENT_ID] == "agent_b"
        proc.on_end(entry)
        segments = json.loads(
            str(session_span._attributes[ATTR_SESSION_INTENT_SEQUENCE])
        )
        assert len(segments) >= 2
        assert segments[1]["from_turn"] == 3
        assert segments[1]["agent_id"] == "agent_b"

    def test_agent_reentry_two_segments(self) -> None:
        proc, _exporter = _proc_with_exporter()
        entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "job-intent-5"})
        proc.on_start(entry)
        session_span = get_job_bootstrap().session_span
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-5",
                    ATTR_LK_AGENT_LABEL: "agent_a",
                    ATTR_LK_USER_TRANSCRIPT: "a",
                },
            )
        )
        proc.on_end(
            _make_span(
                "lk.agent_handoff",
                {
                    ATTR_LK_JOB_ID: "job-intent-5",
                    ATTR_AGENT_TRANSFER_FROM: "agent_a",
                    ATTR_AGENT_TRANSFER_TO: "agent_b",
                },
            )
        )
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-5",
                    ATTR_LK_AGENT_LABEL: "agent_b",
                    ATTR_LK_USER_TRANSCRIPT: "b",
                },
            )
        )
        proc.on_end(
            _make_span(
                "lk.agent_handoff",
                {
                    ATTR_LK_JOB_ID: "job-intent-5",
                    ATTR_AGENT_TRANSFER_FROM: "agent_b",
                    ATTR_AGENT_TRANSFER_TO: "agent_a",
                },
            )
        )
        proc.on_end(
            _make_span(
                "user_turn",
                {
                    ATTR_LK_JOB_ID: "job-intent-5",
                    ATTR_LK_AGENT_LABEL: "agent_a",
                    ATTR_LK_USER_TRANSCRIPT: "c",
                },
            )
        )
        proc.on_end(entry)
        segments = json.loads(
            str(session_span._attributes[ATTR_SESSION_INTENT_SEQUENCE])
        )
        assert len(segments) == 3
        assert segments[0]["agent_id"] == "agent_a"
        assert segments[1]["agent_id"] == "agent_b"
        assert segments[2]["agent_id"] == "agent_a"
        assert segments[0]["segment_index"] == 0
        assert segments[2]["segment_index"] == 2
