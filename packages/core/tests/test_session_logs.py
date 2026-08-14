"""SessionLogHandler buffering and session correlation."""

from __future__ import annotations

import logging

import pytest

from parlot.core.session import SessionState, clear_active_session, set_active_session
from parlot.core.session_logs import (
    SessionLogHandler,
    drain_session_logs,
    set_capture_logs_configure,
    shutdown_session_logs,
)


@pytest.fixture(autouse=True)
def _reset_logs():
    set_capture_logs_configure(True, log_level="DEBUG")
    drain_session_logs()
    clear_active_session()
    yield
    drain_session_logs()
    clear_active_session()
    set_capture_logs_configure(None)
    shutdown_session_logs()


def test_handler_stamps_session_and_buffers() -> None:
    state = SessionState(session_id="abc123", turn_count=2)
    set_active_session(None, state)
    handler = SessionLogHandler()
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
    events = drain_session_logs()
    assert len(events) == 1
    assert events[0].session_id == "abc123"
    assert events[0].message == "hello world"
    assert events[0].level == "INFO"
    assert events[0].logger_name == "my.agent"
    assert events[0].turn_index == 2


def test_handler_drops_without_session() -> None:
    clear_active_session()
    handler = SessionLogHandler()
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
    assert drain_session_logs() == []


def test_handler_respects_min_level() -> None:
    set_capture_logs_configure(True, log_level="WARNING")
    state = SessionState(session_id="sess")
    set_active_session(None, state)
    handler = SessionLogHandler()
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
    events = drain_session_logs()
    assert len(events) == 1
    assert events[0].message == "warn"


def test_handler_noops_when_policy_off() -> None:
    set_capture_logs_configure(False)
    state = SessionState(session_id="sess")
    set_active_session(None, state)
    handler = SessionLogHandler()
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
    assert drain_session_logs() == []


def test_handler_never_raises() -> None:
    handler = SessionLogHandler()
    # Broken record-like object should not propagate.
    handler.emit(None)  # type: ignore[arg-type]
