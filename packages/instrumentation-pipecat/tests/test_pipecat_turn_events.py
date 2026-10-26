"""Aggregator turn events mint ``parlot.turn`` (not STT / native-turn spans)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import set_span_in_context

from parlot.core.attrs import (
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_INTERRUPTED,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_USER_TEXT,
    SPAN_PARLOT_TURN,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
)
from parlot.core.session import clear_active_session
from parlot.instrumentation.pipecat._processor import PipecatGenAIProcessor
from parlot.instrumentation.pipecat._session import (
    _sessions_by_conversation,
    close_session,
    ensure_session,
    set_identity,
    set_tracer,
)
from parlot.instrumentation.pipecat._turn_events import (
    handle_assistant_turn_stopped,
    handle_user_turn_message_added,
    handle_user_turn_stopped,
)
from parlot.instrumentation.pipecat.attrs import (
    ATTR_PIPECAT_CONVERSATION_ID,
    ATTR_PIPECAT_TEXT,
    ATTR_PIPECAT_TRANSCRIPT,
    ATTR_PIPECAT_TURN_NUMBER,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_session()
    _sessions_by_conversation.clear()
    yield
    for cid in list(_sessions_by_conversation):
        close_session(cid, reason="test_teardown")
    _sessions_by_conversation.clear()
    clear_active_session()


def _provider() -> tuple[InMemorySpanExporter, TracerProvider]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(PipecatGenAIProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter, provider


def _user_msg(*, content: str | None, timestamp: str = "2026-01-15T12:00:00.000+00:00"):
    return SimpleNamespace(content=content, timestamp=timestamp, user_id=None)


def _asst_msg(
    *,
    content: str,
    interrupted: bool = False,
    timestamp: str = "2026-01-15T12:00:01.000+00:00",
):
    return SimpleNamespace(content=content, interrupted=interrupted, timestamp=timestamp)


def test_aggregator_events_mint_alternating_user_agent_turns() -> None:
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")
    ensure_session("conv-events")

    handle_user_turn_stopped(None, None, _user_msg(content="hello there"))
    handle_assistant_turn_stopped(
        None, _asst_msg(content="hi friend", interrupted=False)
    )

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 2
    by_role = {s.attributes[ATTR_TURN_PARTICIPANT_ROLE]: s for s in turns}
    assert by_role["user"].attributes[ATTR_TURN_INDEX] == 1
    assert by_role["user"].attributes[ATTR_TURN_USER_TEXT] == "hello there"
    assert by_role["agent"].attributes[ATTR_TURN_INDEX] == 2
    assert by_role["agent"].attributes[ATTR_TURN_AGENT_TEXT] == "hi friend"
    assert not by_role["agent"].attributes.get(ATTR_TURN_INTERRUPTED)


def test_assistant_interrupted_flag() -> None:
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")
    ensure_session("conv-int")

    handle_assistant_turn_stopped(
        None, _asst_msg(content="How can I help—", interrupted=True)
    )

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 1
    assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
    assert turns[0].attributes[ATTR_TURN_INDEX] == 1
    assert turns[0].attributes[ATTR_TURN_INTERRUPTED] is True


def test_premature_native_turn_does_not_mint() -> None:
    """STT + native turn end alone must not mint; aggregator events still do."""
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    conv = tracer.start_span("conversation")
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    turn = tracer.start_span("turn", context=set_span_in_context(conv))
    turn.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    turn.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)

    stt = tracer.start_span("stt", context=set_span_in_context(turn))
    stt.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "It really does")
    stt.end()
    turn.end()  # premature native close — previously raced orphan mint

    turns_before = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert turns_before == []

    handle_user_turn_stopped(None, None, _user_msg(content="It really does"))
    handle_assistant_turn_stopped(
        None, _asst_msg(content="Would you like to know anything else?")
    )

    finished = list(exporter.get_finished_spans())
    turns = [s for s in finished if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 2
    by_role = {s.attributes[ATTR_TURN_PARTICIPANT_ROLE]: s for s in turns}
    assert by_role["user"].attributes[ATTR_TURN_USER_TEXT] == "It really does"
    assert (
        by_role["agent"].attributes[ATTR_TURN_AGENT_TEXT]
        == "Would you like to know anything else?"
    )

    stt_span = next(s for s in finished if s.name == SPAN_VOICE_STT)
    assert stt_span.attributes[ATTR_SESSION_ID]
    assert stt_span.attributes[ATTR_TURN_USER_TEXT] == "It really does"

    conv.end()


def test_realtime_stopped_none_then_message_added_mints_once() -> None:
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")
    ensure_session("conv-rt")

    # Realtime: stopped fires with content=None; message_added has the text.
    handle_user_turn_stopped(None, None, _user_msg(content=None))
    assert [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN] == []

    handle_user_turn_message_added(None, _user_msg(content="hey realtime"))
    # Cascade also fires message_added after stopped with content — must dedup.
    handle_user_turn_stopped(None, None, _user_msg(content="hey realtime"))
    handle_user_turn_message_added(None, _user_msg(content="hey realtime"))

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 1
    assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
    assert turns[0].attributes[ATTR_TURN_USER_TEXT] == "hey realtime"
    assert turns[0].attributes[ATTR_TURN_INDEX] == 1


def test_stt_tts_nest_under_open_agent_index_without_minting() -> None:
    """Pipeline spans stamp turn.index from reserved slots; they do not mint."""
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    conv = tracer.start_span("conversation")
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-nest")
    ensure_session("conv-nest")

    handle_user_turn_stopped(None, None, _user_msg(content="hello"))

    turn = tracer.start_span("turn", context=set_span_in_context(conv))
    turn.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-nest")
    turn.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)

    stt = tracer.start_span("stt", context=set_span_in_context(turn))
    stt.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "hello")
    stt.end()

    tts = tracer.start_span("tts", context=set_span_in_context(turn))
    tts.set_attribute(ATTR_PIPECAT_TEXT, "hi")
    tts.end()

    handle_assistant_turn_stopped(None, _asst_msg(content="hi"))
    turn.end()
    conv.end()

    finished = list(exporter.get_finished_spans())
    turns = [s for s in finished if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 2

    stt_span = next(s for s in finished if s.name == SPAN_VOICE_STT)
    tts_span = next(s for s in finished if s.name == SPAN_VOICE_TTS)
    # Nested under reserved agent index (user=1, agent=2).
    assert stt_span.attributes[ATTR_TURN_INDEX] == 2
    assert tts_span.attributes[ATTR_TURN_INDEX] == 2


def test_empty_assistant_content_skipped() -> None:
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")
    ensure_session("conv-empty")

    handle_assistant_turn_stopped(None, _asst_msg(content="   "))
    assert [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN] == []
