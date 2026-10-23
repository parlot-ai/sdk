"""Tests for ConversationSessionRegistry."""

from __future__ import annotations

from dataclasses import dataclass

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.session import SessionState, get_active_session
from parlot.core.session_lifecycle import start_parlot_session_span
from parlot.core.session_registry import ConversationSessionRegistry


@dataclass
class _State(SessionState):
    conversation_id: str = ""


def test_registry_ensure_get_close() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    registry: ConversationSessionRegistry[_State] = ConversationSessionRegistry()

    def _factory():
        state = _State(session_id="", conversation_id="c1", framework="test")
        span, sid = start_parlot_session_span(tracer, conversation_id="c1")
        state.session_id = sid
        return span, state

    state = registry.ensure("c1", _factory)
    assert state is not None
    assert registry.get_state("c1") is state
    assert get_active_session() is state
    again = registry.ensure("c1", _factory)
    assert again is state

    closed: list[str] = []

    def _closer(span, st: _State) -> None:
        closed.append(st.conversation_id)
        registry.end_and_clear(span, st)

    assert registry.close("c1", closer=_closer, clear_active=False) is True
    assert closed == ["c1"]
    assert registry.get_state("c1") is None
    assert get_active_session() is None
