"""Session log capture policy helpers shared across Parlot integrations.

Default ON when bootstrap is missing or globs are unset. Empty globs = off.
Precedence: job metadata > ``parlotize(capture_logs=…)`` > Settings bootstrap > on.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Optional, Union

from parlot.core.recording import matches_allowlist

CaptureLogsConfig = Union[bool, Sequence[str], None]

DEFAULT_LOGS_GLOBS: tuple[str, ...] = ("*",)
DEFAULT_LOGS_MIN_LEVEL = "INFO"

_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "WARN": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def normalize_log_level(level: str | None) -> str:
    if not level:
        return DEFAULT_LOGS_MIN_LEVEL
    upper = str(level).strip().upper()
    if upper == "WARN":
        return "WARNING"
    if upper in _LEVEL_ORDER:
        return upper if upper != "WARN" else "WARNING"
    return DEFAULT_LOGS_MIN_LEVEL


def level_at_least(level: str, minimum: str) -> bool:
    return _LEVEL_ORDER.get(normalize_log_level(level), 0) >= _LEVEL_ORDER.get(
        normalize_log_level(minimum), 20
    )


def should_capture_logs(
    agent_name: str,
    *,
    metadata_capture_logs: Optional[bool] = None,
    parlotize_capture_logs: CaptureLogsConfig = None,
    bootstrap_globs: Optional[Sequence[str]] = None,
    bootstrap_agents: Optional[Mapping[str, bool]] = None,
    bootstrap_present: bool = False,
) -> bool:
    """Return True when application logs should be captured for this job.

    Precedence: job metadata > ``parlotize(capture_logs=…)`` > bootstrap (UI).
    When bootstrap is absent (``bootstrap_present=False``) or globs are unset,
    default is **on**. Explicit empty globs means off.
    """
    if metadata_capture_logs is False:
        return False
    if metadata_capture_logs is True:
        return True

    if parlotize_capture_logs is not None:
        if isinstance(parlotize_capture_logs, bool):
            return parlotize_capture_logs
        return matches_allowlist(agent_name, list(parlotize_capture_logs))

    agents = bootstrap_agents or {}
    if agent_name in agents:
        return bool(agents[agent_name])

    if not bootstrap_present:
        return True

    if bootstrap_globs is None:
        return True

    globs = list(bootstrap_globs)
    if not globs:
        return False
    return matches_allowlist(agent_name, globs)
