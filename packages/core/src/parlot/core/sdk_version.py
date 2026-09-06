"""Parlot SDK (parlot-core) version resolution and session stamping."""

from __future__ import annotations

from importlib import metadata
from typing import Any

from parlot.core.attrs import ATTR_PARLOT_SDK_VERSION, ATTR_SESSION_METADATA_SDK_VERSION

_MAX_VERSION_LEN = 64
_PARLOT_CORE_DIST = "parlot-core"

_cached_version: str | None = None


def _normalize_version(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if len(stripped) > _MAX_VERSION_LEN:
        return stripped[:_MAX_VERSION_LEN]
    return stripped


def resolve_parlot_sdk_version() -> str:
    """Return installed parlot-core version, cached after first call."""
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    try:
        _cached_version = _normalize_version(metadata.version(_PARLOT_CORE_DIST))
    except metadata.PackageNotFoundError:
        _cached_version = ""

    return _cached_version


def stamp_session_sdk_version(session_span: Any, state: Any | None = None) -> None:
    """Stamp ``parlot.sdk.version`` and ``session.metadata.sdk_version`` on the session span and state."""
    version = resolve_parlot_sdk_version()
    if not version:
        return

    if isinstance(session_span, dict):
        session_span[ATTR_PARLOT_SDK_VERSION] = version
        session_span[ATTR_SESSION_METADATA_SDK_VERSION] = version
    elif session_span is not None and hasattr(session_span, "set_attribute"):
        session_span.set_attribute(ATTR_PARLOT_SDK_VERSION, version)
        session_span.set_attribute(ATTR_SESSION_METADATA_SDK_VERSION, version)

    if state is None:
        try:
            from parlot.core.session import get_active_session

            state = get_active_session()
        except Exception:
            state = None

    if state is not None and hasattr(state, "custom_metadata") and isinstance(state.custom_metadata, dict):
        state.custom_metadata[ATTR_SESSION_METADATA_SDK_VERSION] = version
