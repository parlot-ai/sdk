"""Tests for platform.ref helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from parlot.core.attrs import (
    ATTR_PLATFORM_FRAMEWORK,
    ATTR_PLATFORM_KIND,
    ATTR_PLATFORM_VALUE,
)
from parlot.core.platform_refs import add_platform_ref, stamp_platform_refs
from parlot.core.session import _active_session_span


def test_stamp_platform_refs_uses_set_attribute_on_live_span() -> None:
    span = MagicMock()
    stamp_platform_refs(span, [("custom", "crm_ticket", "TKT-9")])
    span.set_attribute.assert_any_call(ATTR_PLATFORM_FRAMEWORK, "custom")
    span.set_attribute.assert_any_call(ATTR_PLATFORM_KIND, "crm_ticket")
    span.set_attribute.assert_any_call(ATTR_PLATFORM_VALUE, "TKT-9")
    span.set_attribute.assert_any_call("platform.ref.crm_ticket", "TKT-9")


def test_add_platform_ref_stamps_active_session() -> None:
    span = MagicMock()
    token = _active_session_span.set(span)
    try:
        add_platform_ref("order_id", "ORD-1", framework="shopify")
        span.set_attribute.assert_any_call("platform.ref.order_id", "ORD-1")
        span.set_attribute.assert_any_call(ATTR_PLATFORM_FRAMEWORK, "shopify")
    finally:
        _active_session_span.reset(token)
