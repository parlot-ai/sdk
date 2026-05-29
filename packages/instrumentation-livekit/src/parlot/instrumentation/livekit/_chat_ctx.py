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
