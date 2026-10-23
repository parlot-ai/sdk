"""Regression: reminted contract spans must survive PipecatGenAIProcessor."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
    SPAN_PARLOT_TURN,
)
from parlot.core.session import clear_active_session
from parlot.instrumentation.pipecat._processor import PipecatGenAIProcessor
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


def test_processor_does_not_drop_minted_contract_spans() -> None:
    """Bug: remap treated parlot.* as unknown and renamed them to __parlot_drop_*."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    # Same order as production: enrich/remap first, then export.
    provider.add_span_processor(PipecatGenAIProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer(provider.get_tracer("test"))
    set_identity("pipecat-test", "0.1.0")

    state = ensure_session("conv-passthrough")
    assert state is not None
    emit_turn(state, turn_index=1, role="agent")
    close_session("conv-passthrough", reason="completed")

    names = [s.name for s in exporter.get_finished_spans()]
    assert SPAN_CONVERSATION_SESSION in names
    assert SPAN_PARLOT_TURN in names
    assert SPAN_PARLOT_SESSION_CLOSE in names
    assert not any(n.startswith("__parlot_drop_") for n in names)
