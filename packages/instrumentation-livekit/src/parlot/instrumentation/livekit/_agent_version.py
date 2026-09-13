"""Agent deployment version resolution for Parlot instrumentation."""

from __future__ import annotations

from typing import Optional

_MAX_VERSION_LEN = 64
_DEFAULT_VERSION = "unknown"


def _normalize_version(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if len(stripped) > _MAX_VERSION_LEN:
        return stripped[:_MAX_VERSION_LEN]
    return stripped


def resolve_agent_version(explicit: Optional[str]) -> str:
    """Return deployment version for ``gen_ai.agent.version``.

    Uses ``parlotize(version=...)`` when non-empty; otherwise ``\"unknown\"``.
    """
    if explicit is not None:
        normalized = _normalize_version(explicit)
        if normalized:
            return normalized
    return _DEFAULT_VERSION
