"""Tests for Pipecat session / turn minting."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_ID,
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
