"""Intent label derivation from agent id + instructions excerpt."""

from __future__ import annotations

import re

INTENT_LABEL_MAX = 80
INSTRUCTIONS_EXCERPT_MAX = 2000


def _normalize_key(agent_id: str) -> str:
    return agent_id.strip().lower().replace(" ", "_")


def _title_from_id(intent_key: str) -> str:
    if not intent_key or intent_key == "unknown":
        return "Unknown"
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), intent_key.replace("_", " "))


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _first_line(text: str) -> str:
    for line in re.split(r"[\r\n]+", text):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def derive_intent(agent_id: str, instructions: str = "") -> dict[str, str]:
    """Port of platform ingest ``deriveIntent``."""
    aid = agent_id.strip()
    intent_key = _normalize_key(aid) if aid else "unknown"
    excerpt = _truncate(instructions.strip(), INSTRUCTIONS_EXCERPT_MAX) if instructions.strip() else ""

    if excerpt:
        first = _first_line(excerpt)
        intent_label = _truncate(first, INTENT_LABEL_MAX) if first else _title_from_id(intent_key)
    else:
        intent_label = _title_from_id(intent_key)

    return {
        "intent_key": intent_key,
        "intent_label": intent_label,
        "instructions_excerpt": excerpt,
    }
