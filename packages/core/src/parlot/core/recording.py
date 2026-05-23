"""Recording policy helpers shared across Parlot integrations."""

from __future__ import annotations

import fnmatch
import os
from typing import Optional


def parse_record_agents_env() -> Optional[list[str]]:
    """Parse ``PARLOT_RECORD_AGENTS`` (comma-separated globs, or ``*``)."""
    raw = os.environ.get("PARLOT_RECORD_AGENTS", "").strip()
    if not raw:
        return None
    if raw == "*":
        return ["*"]
    return [part.strip() for part in raw.split(",") if part.strip()]


def should_record(
    agent_name: str,
    *,
    metadata_record: Optional[bool] = None,
    allowlist: Optional[list[str]] = None,
) -> bool:
    """Return True when session audio recording should start for this job."""
    if metadata_record is False:
        return False
    if metadata_record is True:
        return True

    resolved_allowlist = (
        parse_record_agents_env() if allowlist is None else allowlist
    )
    if resolved_allowlist is None:
        return False

    name = agent_name.strip()
    if not name:
        return False

    if "*" in resolved_allowlist:
        return True

    for pattern in resolved_allowlist:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False
