"""Tests for public active-session API."""

from __future__ import annotations

from unittest.mock import MagicMock

from parlot.core.session import (
    SessionState,
    clear_active_session,
    get_active_session,
    get_active_session_span,
    session_owned,
    set_active_session,
)


def test_set_and_clear_active_session() -> None:
    clear_active_session()
    assert get_active_session() is None
    assert not session_owned()

    span = MagicMock()
    state = SessionState(session_id="s1", framework="livekit")
    set_active_session(span, state)
    assert get_active_session() is state
    assert get_active_session_span() is span
    assert session_owned()
    assert session_owned(framework="livekit")
    assert not session_owned(framework="langgraph")

    clear_active_session()
    assert get_active_session() is None
    assert not session_owned()


def test_session_owned_requires_session_id() -> None:
    clear_active_session()
    set_active_session(MagicMock(), SessionState(framework="livekit"))
    assert not session_owned()
    clear_active_session()
