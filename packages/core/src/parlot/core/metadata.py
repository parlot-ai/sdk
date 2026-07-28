"""Session custom-metadata helpers — framework-agnostic public API."""

from __future__ import annotations

from typing import Mapping

from parlot.core.attrs import ATTR_SESSION_METADATA_PREFIX
from parlot.core.session import _active_session_span, _active_session_state


def session_metadata_key(key: str) -> str:
    """Return the full ``session.metadata.<key>`` attribute name."""
    cleaned = str(key or "").strip().lstrip(".")
    if cleaned.startswith(ATTR_SESSION_METADATA_PREFIX):
        return cleaned
    return f"{ATTR_SESSION_METADATA_PREFIX}{cleaned}"


def set_session_attribute(key: str, value: str | int | float | bool) -> None:
    """
    Stamp one custom attribute on the active session under ``session.metadata.*``.

    Keys are normalized to ``session.metadata.<key>``. Values are stored as
    strings on the live session span and remembered on session state so they
    are also present on ``parlot.session.close``.
    """
    full_key = session_metadata_key(key)
    if not full_key or full_key == ATTR_SESSION_METADATA_PREFIX:
        return
    str_value = value if isinstance(value, str) else str(value)

    state = _active_session_state.get()
    if state is not None:
        state.custom_metadata[full_key] = str_value

    span = _active_session_span.get()
    if span is not None and hasattr(span, "set_attribute"):
        span.set_attribute(full_key, str_value)


def set_session_metadata(**pairs: str | int | float | bool) -> None:
    """
    Attach custom key/value metadata to the active Parlot session.

    Each keyword becomes ``session.metadata.<name>`` on the session span and
    appears in session detail in the Parlot UI.

    Example::

        from parlot.instrumentation.livekit import set_session_metadata

        set_session_metadata(order_id="12345", crm_ticket="TKT-9")
    """
    for key, value in pairs.items():
        set_session_attribute(key, value)


def stamp_session_metadata_attrs(
    attrs: dict[str, object],
    metadata: Mapping[str, str] | None,
) -> None:
    """Merge remembered ``session.metadata.*`` pairs into a close-span attr dict."""
    if not metadata:
        return
    for key, value in metadata.items():
        if key.startswith(ATTR_SESSION_METADATA_PREFIX) and key not in attrs:
            attrs[key] = value
