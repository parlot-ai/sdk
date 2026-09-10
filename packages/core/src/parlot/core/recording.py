"""Recording policy helpers shared across Parlot integrations."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from typing import Optional, Union

RecordConfig = Union[bool, Sequence[str], None]


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
    record_config: RecordConfig = None,
    bootstrap_globs: Optional[Sequence[str]] = None,
    bootstrap_agents: Optional[Mapping[str, bool]] = None,
) -> bool:
    """Return True when session audio recording should start for this job.

    Precedence: job metadata > ``parlotize(record=…)`` > bootstrap (UI) policy.
    """
    if metadata_record is False:
        return False
    if metadata_record is True:
        return True

    if record_config is not None:
        if isinstance(record_config, bool):
            return record_config
        return matches_allowlist(agent_name, list(record_config))

    agents = bootstrap_agents or {}
    if agent_name in agents:
        return bool(agents[agent_name])

    globs = list(bootstrap_globs or ())
    if not globs:
        return False
    return matches_allowlist(agent_name, globs)
