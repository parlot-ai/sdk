"""LiveKit chat context parsing helpers."""

from __future__ import annotations

import json
import re
from typing import Any


def _normalize_instruction_block(text: str) -> str:
    """Trim, normalize line endings, and collapse excessive blank lines."""
    text = text.strip().replace("\r\n", "\n")
    return re.sub(r"\n{3,}", "\n\n", text)


def _dedupe_instruction_blocks(parts: list[str]) -> list[str]:
    """Preserve first-seen order while dropping normalized duplicate blocks."""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        block = _normalize_instruction_block(part)
        if not block or block in seen:
            continue
        seen.add(block)
        out.append(block)
    return out


def _collect_config_update_parts(raw: str) -> list[str]:
    parts: list[str] = []
    for item in parse_chat_ctx_agent_config_updates(raw):
        instructions = item.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            parts.append(instructions)
    return parts


def _collect_system_message_parts(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    parts: list[str] = []
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
            parts.append(text)
    return parts


def _join_and_truncate(parts: list[str], *, max_chars: int) -> str:
    unique_parts = _dedupe_instruction_blocks(parts)
    if not unique_parts:
        return ""
    joined = "\n\n".join(unique_parts)
    if len(joined) <= max_chars:
        return joined
    return f"{joined[: max_chars - 3]}..."


def parse_chat_ctx_agent_config_updates(raw: str) -> list[dict[str, Any]]:
    """Extract ``agent_config_update`` items from LiveKit chat_ctx JSON.

    Accepts payload from ``lk.pii.chat_ctx`` (Agents 1.7+) or legacy ``lk.chat_ctx``.
    """
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
    """Full excerpt: agent_config_update instructions + runtime system messages."""
    parts = _collect_config_update_parts(raw) + _collect_system_message_parts(raw)
    return _join_and_truncate(parts, max_chars=max_chars)


def static_instructions_excerpt_from_chat_ctx(
    raw: str,
    *,
    max_chars: int = 2000,
) -> str:
    """Static excerpt: agent_config_update instructions only (no runtime system messages)."""
    return _join_and_truncate(_collect_config_update_parts(raw), max_chars=max_chars)


def full_instructions_excerpt(
    chat_raw: str,
    lk_instructions: str = "",
    *,
    max_chars: int = 2000,
) -> str:
    """Full excerpt including lk.instructions, config updates, and runtime system messages."""
    parts: list[str] = []
    if lk_instructions.strip():
        parts.append(lk_instructions.strip())
    if chat_raw:
        parts.extend(_collect_config_update_parts(chat_raw))
        parts.extend(_collect_system_message_parts(chat_raw))
    return _join_and_truncate(parts, max_chars=max_chars)


def static_instructions_excerpt(
    chat_raw: str,
    lk_instructions: str = "",
    *,
    max_chars: int = 2000,
) -> str:
    """Static excerpt including lk.instructions and config updates only."""
    parts: list[str] = []
    if lk_instructions.strip():
        parts.append(lk_instructions.strip())
    if chat_raw:
        parts.extend(_collect_config_update_parts(chat_raw))
    return _join_and_truncate(parts, max_chars=max_chars)

