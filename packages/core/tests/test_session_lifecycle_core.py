"""Tests for OTLP flush and session close helpers."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_SESSION_CLOSE_REASON,
    ATTR_SESSION_ID,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
)
from parlot.core.session_lifecycle import (
    emit_parlot_session_close,
    force_flush_tracer_provider,
    force_flush_with_budget,
    start_parlot_session_span,
)


def test_force_flush_tracer_provider_ok() -> None:
    provider = TracerProvider()
    assert force_flush_tracer_provider(provider, timeout_millis=100) is True


def test_force_flush_with_budget_uses_flush_fn() -> None:
    calls: list[int] = []

    def _flush(*, timeout_millis: int) -> bool:
        calls.append(timeout_millis)
        return False

    ok = force_flush_with_budget(
        budget_s=0.05,
        backoffs_s=(0.01,),
        attempt_timeout_ms=20,
        flush_fn=_flush,
    )
    assert ok is False
    assert len(calls) >= 1


def test_start_and_close_session_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    stamped: list[str] = []

    def _stamp(span) -> None:
        stamped.append(span.name)
        span.set_attribute("agent.framework", "test")

    session_span, session_id = start_parlot_session_span(
        tracer,
        conversation_id="c1",
        stamp_fn=_stamp,
    )
    assert session_id
    assert stamped == [SPAN_CONVERSATION_SESSION]
    emit_parlot_session_close(
        tracer,
        session_id=session_id,
        conversation_id="c1",
        reason="completed",
        framework="test",
        stamp_fn=_stamp,
        copy_from_session_span=session_span,
    )
    session_span.end()
    names = [s.name for s in exporter.get_finished_spans()]
    assert SPAN_PARLOT_SESSION_CLOSE in names
    close = next(s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_SESSION_CLOSE)
    assert close.attributes[ATTR_SESSION_ID] == session_id
    assert close.attributes[ATTR_SESSION_CLOSE_REASON] == "completed"
