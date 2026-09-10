"""SessionLogHandler buffering and session correlation."""

from __future__ import annotations

import logging
import time

import pytest

from parlot.core.context import ParlotContext
from parlot.core.session import SessionState, clear_active_session, set_active_session
from parlot.core.session_logs import SessionLogHandler


@pytest.fixture
def ctx() -> ParlotContext:
    context = ParlotContext()
    context.session_logs.set_capture_logs_config(True, log_level="DEBUG")
    clear_active_session()
    yield context
    clear_active_session()
    context.shutdown()


def test_handler_stamps_session_and_buffers(ctx: ParlotContext) -> None:
    state = SessionState(session_id="abc123", turn_count=2)
    set_active_session(None, state)
    handler = SessionLogHandler(ctx.session_logs)
    record = logging.LogRecord(
        name="my.agent",
        level=logging.INFO,
        pathname="agent.py",
        lineno=10,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    events = ctx.session_logs.drain()
    assert len(events) == 1
    assert events[0].session_id == "abc123"
    assert events[0].message == "hello world"
    assert events[0].level == "INFO"
    assert events[0].logger_name == "my.agent"
    assert events[0].turn_index == 2


def test_handler_drops_without_session(ctx: ParlotContext) -> None:
    clear_active_session()
    handler = SessionLogHandler(ctx.session_logs)
    record = logging.LogRecord(
        name="my.agent",
        level=logging.INFO,
        pathname="agent.py",
        lineno=10,
        msg="orphan",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    assert ctx.session_logs.drain() == []


def test_handler_respects_min_level(ctx: ParlotContext) -> None:
    ctx.session_logs.set_capture_logs_config(True, log_level="WARNING")
    state = SessionState(session_id="sess")
    set_active_session(None, state)
    handler = SessionLogHandler(ctx.session_logs)
    info = logging.LogRecord(
        name="my.agent",
        level=logging.INFO,
        pathname="a.py",
        lineno=1,
        msg="info",
        args=(),
        exc_info=None,
    )
    warn = logging.LogRecord(
        name="my.agent",
        level=logging.WARNING,
        pathname="a.py",
        lineno=2,
        msg="warn",
        args=(),
        exc_info=None,
    )
    handler.emit(info)
    handler.emit(warn)
    events = ctx.session_logs.drain()
    assert len(events) == 1
    assert events[0].message == "warn"


def test_handler_noops_when_policy_off(ctx: ParlotContext) -> None:
    ctx.session_logs.set_capture_logs_config(False)
    state = SessionState(session_id="sess")
    set_active_session(None, state)
    handler = SessionLogHandler(ctx.session_logs)
    record = logging.LogRecord(
        name="my.agent",
        level=logging.ERROR,
        pathname="a.py",
        lineno=1,
        msg="fail",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    assert ctx.session_logs.drain() == []


def test_handler_never_raises(ctx: ParlotContext) -> None:
    handler = SessionLogHandler(ctx.session_logs)
    # Broken record-like object should not propagate.
    handler.emit(None)  # type: ignore[arg-type]


def test_shutdown_flushes_remaining_logs(
    ctx: ParlotContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted: list = []

    def fake_post(events: list) -> bool:
        posted.extend(events)
        return True

    logs = ctx.session_logs
    monkeypatch.setattr(logs, "_endpoint", "http://localhost:4318")
    monkeypatch.setattr(logs, "_api_key", "test-key")
    monkeypatch.setattr(logs, "_last_flush_at", time.time())
    monkeypatch.setattr(logs, "_circuit_open_until", 0.0)
    monkeypatch.setattr(logs, "_post_events", fake_post)

    set_active_session(None, SessionState(session_id="sess-final"))
    handler = SessionLogHandler(logs)
    handler.emit(
        logging.LogRecord(
            name="my.agent",
            level=logging.INFO,
            pathname="agent.py",
            lineno=20,
            msg="late log",
            args=(),
            exc_info=None,
        )
    )
    assert len(logs.snapshot()) == 1

    logs._try_flush()
    assert posted == []
    assert len(logs.snapshot()) == 1

    logs.shutdown()
    assert [event.message for event in posted] == ["late log"]
    assert logs.drain() == []


def test_two_contexts_isolate_session_logs() -> None:
    a = ParlotContext()
    b = ParlotContext()
    a.session_logs.set_capture_logs_config(True, log_level="DEBUG")
    b.session_logs.set_capture_logs_config(True, log_level="DEBUG")
    set_active_session(None, SessionState(session_id="sess"))
    try:
        SessionLogHandler(a.session_logs).emit(
            logging.LogRecord(
                name="my.agent",
                level=logging.INFO,
                pathname="a.py",
                lineno=1,
                msg="a-log",
                args=(),
                exc_info=None,
            )
        )
        SessionLogHandler(b.session_logs).emit(
            logging.LogRecord(
                name="my.agent",
                level=logging.INFO,
                pathname="b.py",
                lineno=1,
                msg="b-log",
                args=(),
                exc_info=None,
            )
        )
        assert [e.message for e in a.session_logs.drain()] == ["a-log"]
        assert [e.message for e in b.session_logs.drain()] == ["b-log"]
    finally:
        clear_active_session()
        a.shutdown()
        b.shutdown()


def test_encode_otlp_logs_protobuf() -> None:
    from parlot.core.session_logs import SessionLogRecord, _encode_otlp_logs

    payload = _encode_otlp_logs(
        [
            SessionLogRecord(
                session_id="s1",
                conversation_id="c1",
                ts="2026-01-01 12:00:00.123",
                level="INFO",
                logger_name="my.agent",
                message="hello otlp",
                turn_index=3,
                trace_id="aabbccddeeff00112233445566778899",
                span_id="1122334455667788",
                attributes={"pathname": "agent.py"},
            )
        ]
    )
    assert isinstance(payload, (bytes, bytearray))
    assert len(payload) > 40
    assert b"hello otlp" in payload
    assert b"session.id" in payload or b"s1" in payload
