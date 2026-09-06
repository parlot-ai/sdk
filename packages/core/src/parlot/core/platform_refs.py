"""
Parlot platform.ref.* helpers for session resolve / debug linking.

Framework-agnostic span stamping only. Framework-specific registries and
triple construction live in each instrumentation package (e.g. LiveKit).
"""

from __future__ import annotations

from typing import Any

from .attrs import (
    ATTR_PLATFORM_FRAMEWORK,
    ATTR_PLATFORM_KIND,
    ATTR_PLATFORM_REF_PREFIX,
    ATTR_PLATFORM_VALUE,
)
from .session import get_active_session_span


def platform_ref_flat_key(kind: str) -> str:
    """Flat ``platform.ref.{kind}`` attribute key for ingestion fallbacks."""
    return f"{ATTR_PLATFORM_REF_PREFIX}{kind}"


def stamp_platform_refs(
    span: Any,
    refs: list[tuple[str, str, str]],
) -> None:
    """Stamp ``platform.ref.*`` triples onto a span.

    ``refs`` is a list of ``(framework, kind, value)`` tuples, e.g.
    ``("livekit", "room_sid", "RM_abc")``. The first tuple is also written
    to the canonical triple attributes (``platform.ref.framework/kind/value``)
    so backends can pivot on a single primary ref.

    Every tuple is also written as a flat ``platform.ref.{kind} = value`` key
    for ingestion fallbacks.

    Args:
        span: A live OTel span (``set_attribute``) or a ``ReadableSpan`` with a
            mutable ``_attributes`` dict.
        refs: Non-empty list of reference triples.
    """
    if not refs:
        return

    def _write(key: str, value: str) -> None:
        if hasattr(span, "set_attribute") and callable(span.set_attribute):
            try:
                span.set_attribute(key, value)
                return
            except Exception:
                pass
        if getattr(span, "_attributes", None) is None:
            try:
                span._attributes = {}
            except Exception:
                return
        span._attributes[key] = value

    fw, kind, val = refs[0]
    _write(ATTR_PLATFORM_FRAMEWORK, fw)
    _write(ATTR_PLATFORM_KIND, kind)
    _write(ATTR_PLATFORM_VALUE, val)

    for _fw_i, kind_i, val_i in refs:
        _write(platform_ref_flat_key(kind_i), val_i)


def add_platform_ref(
    kind: str,
    value: str,
    *,
    framework: str = "custom",
) -> None:
    """
    Attach a searchable external ID to the active Parlot session.

    Stamps ``platform.ref.{kind}`` (and the primary triple when this is the
    first ref) on the live session span so the session can be found by that
    value in Parlot search / resolve.

    Args:
        kind: Identifier type (e.g. ``"crm_ticket"``, ``"order_number"``,
            ``"call_sid"``).
        value: Unique identifier value (e.g. ``"TKT-9921"``).
        framework: Originating framework name. Defaults to ``"custom"``.

    Example::

        from parlot.instrumentation.livekit import add_platform_ref

        add_platform_ref("crm_ticket", "TKT-9")
    """
    kind = str(kind or "").strip()
    value = str(value or "").strip()
    framework = str(framework or "custom").strip() or "custom"
    if not kind or not value:
        return
    span = get_active_session_span()
    if span is None:
        return
    stamp_platform_refs(span, [(framework, kind, value)])
