"""GenAI message + tool payload capture policy (platform-agnostic).

Content capture **on** — emit GenAI message event bodies and tool
request/response payloads on spans.

Content capture **off** — omit those bodies. Still emit span structure,
timings, token/usage metrics, tool names/error flags, and contract turn
text (``turn.user_text`` / ``turn.agent_text``).

Not in scope: audio recording, session logs, or instruction excerpts.

Precedence: ``configure(capture_content=…)`` > Settings bootstrap > on.
Default ON when bootstrap is missing. Explicit empty globs = off.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Optional

from parlot.core.recording import matches_allowlist

DEFAULT_CAPTURE_CONTENT_GLOBS: tuple[str, ...] = ("*",)


def should_capture_content(
    agent_name: str,
    *,
    configure_capture_content: Optional[bool] = None,
    bootstrap_globs: Optional[Sequence[str]] = None,
    bootstrap_agents: Optional[Mapping[str, bool]] = None,
    bootstrap_present: bool = False,
) -> bool:
    """Return True when GenAI/tool content bodies should be captured.

    Precedence: ``configure(capture_content=…)`` > bootstrap (UI) > default on.
    When bootstrap is absent (``bootstrap_present=False``) or globs are unset,
    default is **on**. Explicit empty globs means off.
    """
    if configure_capture_content is not None:
        return bool(configure_capture_content)

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
