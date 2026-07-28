"""Tests for session custom metadata helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from parlot.core.attrs import ATTR_SESSION_METADATA_PREFIX
from parlot.core.metadata import (
    session_metadata_key,
    set_session_attribute,
    set_session_metadata,
    stamp_session_metadata_attrs,
)
from parlot.core.session import SessionState, _active_session_span, _active_session_state


def test_session_metadata_key_normalizes() -> None:
    assert session_metadata_key("order_id") == "session.metadata.order_id"
    assert session_metadata_key("session.metadata.order_id") == "session.metadata.order_id"
    assert session_metadata_key(".crm") == "session.metadata.crm"


def test_set_session_metadata_stamps_active_span() -> None:
    span = MagicMock()
    state = SessionState(session_id="abc")
    span_token = _active_session_span.set(span)
    state_token = _active_session_state.set(state)
    try:
        set_session_metadata(order_id="123", retry_count=2)
        set_session_attribute("crm_ticket", "TKT-9")
        span.set_attribute.assert_any_call("session.metadata.order_id", "123")
        span.set_attribute.assert_any_call("session.metadata.retry_count", "2")
        span.set_attribute.assert_any_call("session.metadata.crm_ticket", "TKT-9")
        assert state.custom_metadata["session.metadata.order_id"] == "123"
        assert state.custom_metadata["session.metadata.retry_count"] == "2"
        assert state.custom_metadata["session.metadata.crm_ticket"] == "TKT-9"
    finally:
        _active_session_span.reset(span_token)
        _active_session_state.reset(state_token)


def test_stamp_session_metadata_attrs_fills_missing() -> None:
    attrs: dict[str, object] = {f"{ATTR_SESSION_METADATA_PREFIX}keep": "a"}
    stamp_session_metadata_attrs(
        attrs,
        {
            f"{ATTR_SESSION_METADATA_PREFIX}keep": "b",
            f"{ATTR_SESSION_METADATA_PREFIX}added": "c",
            "ignored": "x",
        },
    )
    assert attrs[f"{ATTR_SESSION_METADATA_PREFIX}keep"] == "a"
    assert attrs[f"{ATTR_SESSION_METADATA_PREFIX}added"] == "c"
    assert "ignored" not in attrs
