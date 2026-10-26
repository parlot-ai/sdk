"""attach_aggregators + fail-soft turn handlers coexist with user handlers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import ATTR_TURN_PARTICIPANT_ROLE, SPAN_PARLOT_TURN
from parlot.core.session import clear_active_session
from parlot.instrumentation.pipecat._hooks import (
    attach_aggregators,
    bind_assistant_aggregator,
    bind_user_aggregator,
)
from parlot.instrumentation.pipecat._session import (
    _sessions_by_conversation,
    close_session,
    ensure_session,
    set_identity,
    set_tracer,
)
from parlot.instrumentation.pipecat._turn_events import (
    handle_user_turn_stopped,
)


class _FakeAggregator:
    """Minimal stand-in for Pipecat BaseObject event wiring."""

    def __init__(self) -> None:
        self.handlers: dict[str, list[Any]] = {}

    def add_event_handler(self, event_name: str, handler: Any) -> None:
        self.handlers.setdefault(event_name, []).append(handler)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_session()
    _sessions_by_conversation.clear()
    yield
    for cid in list(_sessions_by_conversation):
        close_session(cid, reason="test_teardown")
    _sessions_by_conversation.clear()
    clear_active_session()


def test_attach_aggregators_idempotent() -> None:
    user = _FakeAggregator()
    asst = _FakeAggregator()

    assert bind_user_aggregator(user) is True
    assert bind_assistant_aggregator(asst) is True
    assert "on_user_turn_stopped" in user.handlers
    assert "on_assistant_turn_stopped" in asst.handlers
    assert len(user.handlers["on_user_turn_stopped"]) == 1
    assert len(asst.handlers["on_assistant_turn_stopped"]) == 1

    # Second bind / attach is a no-op.
    assert bind_user_aggregator(user) is False
    assert bind_assistant_aggregator(asst) is False
    attach_aggregators(user, asst)
    assert len(user.handlers["on_user_turn_stopped"]) == 1
    assert len(asst.handlers["on_assistant_turn_stopped"]) == 1


def test_attach_alongside_user_handler() -> None:
    user = _FakeAggregator()
    user_calls: list[str] = []

    def user_handler(aggregator: Any, strategy: Any, message: Any) -> None:
        user_calls.append(str(getattr(message, "content", "") or ""))

    user.add_event_handler("on_user_turn_stopped", user_handler)
    attach_aggregators(user_aggregator=user)

    assert len(user.handlers["on_user_turn_stopped"]) == 2
    assert user.handlers["on_user_turn_stopped"][0] is user_handler


def test_fail_soft_user_handler_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer(provider.get_tracer("test"))
    set_identity("pipecat-test", "0.1.0")
    ensure_session("conv-failsoft")

    def boom(*_a: Any, **_k: Any) -> str:
        raise RuntimeError("parlot internal failure")

    monkeypatch.setattr(
        "parlot.instrumentation.pipecat._turn_events.emit_turn",
        boom,
    )

    # Must not raise — fail-soft swallows the error.
    handle_user_turn_stopped(
        None,
        None,
        SimpleNamespace(
            content="hello",
            timestamp="2026-01-15T12:00:00.000+00:00",
            user_id=None,
        ),
    )

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert turns == []


def test_fail_soft_still_allows_user_handler_after_parlot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate Pipecat multi-handler dispatch: Parlot fails, user still runs."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer(provider.get_tracer("test"))
    set_identity("pipecat-test", "0.1.0")
    ensure_session("conv-coexist")

    def boom(*_a: Any, **_k: Any) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "parlot.instrumentation.pipecat._turn_events.emit_turn",
        boom,
    )

    user_seen: list[str] = []

    def user_handler(_agg: Any, _strategy: Any, message: Any) -> None:
        user_seen.append(str(message.content))

    msg = SimpleNamespace(
        content="still here",
        timestamp="2026-01-15T12:00:00.000+00:00",
        user_id=None,
    )
    # Dispatch order: Parlot then user (as after attach_aggregators on a fresh agg).
    handle_user_turn_stopped(None, None, msg)
    user_handler(None, None, msg)

    assert user_seen == ["still here"]
    assert not any(
        s.name == SPAN_PARLOT_TURN
        and s.attributes.get(ATTR_TURN_PARTICIPANT_ROLE) == "user"
        for s in exporter.get_finished_spans()
    )
