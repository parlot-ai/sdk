"""Recording policy helpers shared across Parlot integrations."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from typing import Optional, Union

ConfigureRecord = Union[bool, Sequence[str], None]


def matches_allowlist(agent_name: str, allowlist: Sequence[str]) -> bool:
    """Return True when *agent_name* matches any glob in *allowlist*."""
    if "*" in allowlist:
        return True

    name = agent_name.strip()
    if not name:
        return False

    for pattern in allowlist:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def should_record(
    agent_name: str,
    *,
    metadata_record: Optional[bool] = None,
    configure_record: ConfigureRecord = None,
    bootstrap_globs: Optional[Sequence[str]] = None,
    bootstrap_agents: Optional[Mapping[str, bool]] = None,
) -> bool:
    """Return True when session audio recording should start for this job.

    Precedence: job metadata > ``configure(record=…)`` > bootstrap (UI) policy.
    """
    if metadata_record is False:
        return False
    if metadata_record is True:
        return True

    if configure_record is not None:
        if isinstance(configure_record, bool):
            return configure_record
        return matches_allowlist(agent_name, list(configure_record))

    agents = bootstrap_agents or {}
    if agent_name in agents:
        return bool(agents[agent_name])

    globs = list(bootstrap_globs or ())
    if not globs:
        return False
    return matches_allowlist(agent_name, globs)
