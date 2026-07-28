"""Agent deployment version resolution for Parlot instrumentation."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

_MAX_VERSION_LEN = 64


def _normalize_version(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if len(stripped) > _MAX_VERSION_LEN:
        return stripped[:_MAX_VERSION_LEN]
    return stripped


def _version_from_main() -> str:
    main = sys.modules.get("__main__")
    if main is None:
        return ""
    for attr in ("__version__", "VERSION"):
        val = getattr(main, attr, None)
        if isinstance(val, str) and val.strip():
            return _normalize_version(val)
    return ""


def _version_from_env() -> str:
    return _normalize_version(os.environ.get("PARLOT_AGENT_VERSION", ""))


def _version_from_git() -> str:
    cwd = os.getcwd()
    if not os.path.isdir(os.path.join(cwd, ".git")):
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return _normalize_version(result.stdout)


def resolve_agent_version(explicit: Optional[str]) -> str:
    """Return deployment version or '' if none found.

    Resolution order: explicit kwarg → ``__main__.__version__`` / ``VERSION`` →
    ``PARLOT_AGENT_VERSION`` → local git SHA (dev only).
    """
    if explicit is not None:
        normalized = _normalize_version(explicit)
        if normalized:
            return normalized

    for candidate in (_version_from_main, _version_from_env, _version_from_git):
        normalized = candidate()
        if normalized:
            return normalized

    return ""
