"""Heuristic intent labels from agent id + instructions excerpt (framework-agnostic)."""

from __future__ import annotations

import re

_INTENT_LABEL_MAX = 80
_INSTRUCTIONS_EXCERPT_MAX = 2000


def derive_intent(
    agent_id: str,
    instructions: str = "",
) -> tuple[str, str, str]:
    """
    Return (intent_key, intent_label, instructions_excerpt).

    Empty instructions → title-case from snake_case agent_id.
    Non-empty → first non-empty line for intent_label; capped excerpt for eval.
    """
    aid = agent_id.strip()
    intent_key = _normalize_key(aid) if aid else "unknown"
    excerpt = _first_instructions_excerpt(instructions)

    if excerpt:
        first_line = _first_line(excerpt)
        intent_label = (
            _truncate(first_line, _INTENT_LABEL_MAX)
            if first_line
            else _title_from_id(intent_key)
        )
    else:
        intent_label = _title_from_id(intent_key)

    return intent_key, intent_label, excerpt


def _normalize_key(agent_id: str) -> str:
    return agent_id.strip().lower().replace(" ", "_")


def _title_from_id(intent_key: str) -> str:
    if not intent_key or intent_key == "unknown":
        return "Unknown"
    return intent_key.replace("_", " ").strip().title()


def _first_instructions_excerpt(text: str) -> str:
    raw = str(text).strip()
    if not raw:
        return ""
    return _truncate(raw, _INSTRUCTIONS_EXCERPT_MAX)


def _first_line(text: str) -> str:
    for line in re.split(r"[\r\n]+", text):
        stripped = line.strip()
        if stripped:
            return stripped
    return text.strip()


def _truncate(text: str, limit: int) -> str:
    s = str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."
