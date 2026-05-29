"""LiveKit chat context parsing helpers."""

from __future__ import annotations

import json
from typing import Any


def parse_chat_ctx_agent_config_updates(raw: str) -> list[dict[str, Any]]:
    """Extract ``agent_config_update`` items from LiveKit ``lk.chat_ctx`` JSON."""
    if not raw:
        return []
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("type") == "agent_config_update":
            out.append(item)
    return out


def instructions_excerpt_from_chat_ctx(raw: str, *, max_chars: int = 2000) -> str:
    """Best-effort system/instructions text from LiveKit chat context JSON."""
    if not raw:
        return ""
    parts: list[str] = []
    for item in parse_chat_ctx_agent_config_updates(raw):
        instructions = item.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            parts.append(instructions.strip())
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    items = data.get("items") if isinstance(data, dict) else None
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            if item.get("role") != "system":
                continue
            content = item.get("content")
            text = ""
            if isinstance(content, list):
                text = " ".join(str(c) for c in content if c)
            elif content:
                text = str(content)
            if text.strip():
                parts.append(text.strip())
    if not parts:
        return ""
    joined = "\n\n".join(parts)
    if len(joined) <= max_chars:
        return joined
    return f"{joined[: max_chars - 3]}..."
