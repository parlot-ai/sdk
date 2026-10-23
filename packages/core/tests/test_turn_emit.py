"""Tests for shared ``emit_parlot_turn_root`` / utterance stamping."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_USER_TEXT,
    SPAN_PARLOT_TURN,
)
from parlot.core.turn_emit import emit_parlot_turn_root, stamp_turn_utterance_text


def _tracer_and_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("test"), exporter


def test_stamp_turn_utterance_text_by_role() -> None:
    tracer, exporter = _tracer_and_exporter()
    span = tracer.start_span("tmp")
    stamp_turn_utterance_text(span, participant_role="user", utterance_text=" hi ")
    stamp_turn_utterance_text(span, participant_role="agent", utterance_text="hello")
    span.end()
    finished = exporter.get_finished_spans()[0]
    assert finished.attributes[ATTR_TURN_USER_TEXT] == "hi"
    assert finished.attributes[ATTR_TURN_AGENT_TEXT] == "hello"


def test_emit_parlot_turn_root_fresh_trace() -> None:
    tracer, exporter = _tracer_and_exporter()
    tid1, sid1 = emit_parlot_turn_root(
        tracer,
        session_id="s1",
        conversation_id="c1",
        turn_index=1,
        participant_role="user",
        utterance_text="hello",
    )
    tid2, sid2 = emit_parlot_turn_root(
        tracer,
        session_id="s1",
        conversation_id="c1",
        turn_index=2,
        participant_role="agent",
        utterance_text="hi",
    )
    assert tid1 != tid2
    assert len(tid1) == 32 and len(sid1) == 16
    assert len(tid2) == 32 and len(sid2) == 16
    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 2
    assert turns[0].attributes[ATTR_SESSION_ID] == "s1"
    assert turns[0].attributes[ATTR_TURN_INDEX] == 1
    assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
    assert turns[0].attributes[ATTR_TURN_USER_TEXT] == "hello"
    assert turns[1].attributes[ATTR_TURN_AGENT_TEXT] == "hi"


def test_emit_parlot_turn_root_dual_text_and_stamp_fn() -> None:
    tracer, exporter = _tracer_and_exporter()
    stamped: list[str] = []

    def _stamp(span) -> None:
        stamped.append("ok")
        span.set_attribute("custom.ref", "x")

    emit_parlot_turn_root(
        tracer,
        session_id="s1",
        conversation_id="c1",
        turn_index=1,
        participant_role="agent",
        user_text="u",
        agent_text="a",
        stamp_fn=_stamp,
        extra_attrs={"agent.framework": "test"},
    )
    assert stamped == ["ok"]
    turn = exporter.get_finished_spans()[0]
    assert turn.attributes[ATTR_TURN_USER_TEXT] == "u"
    assert turn.attributes[ATTR_TURN_AGENT_TEXT] == "a"
    assert turn.attributes["custom.ref"] == "x"
    assert turn.attributes["agent.framework"] == "test"
