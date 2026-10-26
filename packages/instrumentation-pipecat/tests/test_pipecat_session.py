"""Tests for Pipecat session / turn minting."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_ID,
    ATTR_SESSION_TURN_COUNT,
    ATTR_SESSION_TURN_INDEX_MAX,
    ATTR_TURN_INDEX,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
    SPAN_PARLOT_TURN,
)
from parlot.core.session import clear_active_session
from parlot.instrumentation.pipecat._session import (
    _sessions_by_conversation,
    close_session,
    emit_turn,
    ensure_session,
    set_identity,
    set_tracer,
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


def test_ensure_session_and_turn_emit_contract_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    state = ensure_session("conv-abc")
    assert state is not None
    assert state.session_id
    assert state.framework == "pipecat"

    tid = emit_turn(state, turn_index=1, role="agent")
    assert len(tid) == 32

    close_session("conv-abc", reason="completed")

    names = [s.name for s in exporter.get_finished_spans()]
    assert SPAN_CONVERSATION_SESSION in names
    assert SPAN_PARLOT_TURN in names
    assert SPAN_PARLOT_SESSION_CLOSE in names

    session_spans = [s for s in exporter.get_finished_spans() if s.name == SPAN_CONVERSATION_SESSION]
    assert session_spans[0].attributes[ATTR_SESSION_AGENT_FRAMEWORK] == "pipecat"
    assert session_spans[0].attributes[ATTR_SESSION_ID] == state.session_id

    turn_spans = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert turn_spans[0].attributes[ATTR_TURN_INDEX] == 1

    close_spans = [
        s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_SESSION_CLOSE
    ]
    assert close_spans[0].attributes[ATTR_SESSION_TURN_COUNT] == 1
    assert close_spans[0].attributes[ATTR_SESSION_TURN_INDEX_MAX] == 1


def test_release_agent_turn_reservation_rolls_back_turn_count() -> None:
    from parlot.instrumentation.pipecat._session import (
        allocate_agent_turn_index,
        allocate_user_turn_index,
        release_agent_turn_reservation,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    set_tracer(tracer)

    state = ensure_session("conv-release")
    assert state is not None
    allocate_user_turn_index(state)
    allocate_agent_turn_index(state)
    assert state.turn_count == 2
    assert state.open_user_turn_index == 1
    assert state.open_agent_turn_index == 2

    release_agent_turn_reservation(state)
    assert state.open_agent_turn_index is None
    assert state.open_user_turn_index == 1
    assert state.turn_count == 1
