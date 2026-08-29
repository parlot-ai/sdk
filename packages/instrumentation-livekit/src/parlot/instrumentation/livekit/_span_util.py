"""Shared span attribute helpers for LiveKit GenAI enrichment."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Optional

from opentelemetry.util.types import AttributeValue

_INSTRUCTIONS_EXCERPT_CHARS = 2000
_MAX_TOOL_PAYLOAD_CHARS = 8192
_TOOL_PREVIEW_CHARS = 512
_ASYNC_TOOL_MIN_DURATION_NS = 30_000_000_000
_EXECUTION_START_GAP_NS = 5_000_000_000

AMD_CATEGORY_TO_CONTACT_TYPE: dict[str, str] = {
    "human": "human",
    "machine-ivr": "ivr",
    "machine-vm": "voicemail",
    "machine-unavailable": "unavailable",
    "uncertain": "unknown",
}


def attr_int(
    attrs: Mapping[str, AttributeValue], key: str, default: int = 0
) -> int:
    val = attrs.get(key, default)
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def optional_float(value: AttributeValue | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def provider_to_system(provider: str) -> str:
    mapping = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gcp.vertex_ai",
        "gemini": "gcp.vertex_ai",
        "deepgram": "deepgram",
        "elevenlabs": "elevenlabs",
        "cartesia": "cartesia",
        "assemblyai": "assemblyai",
        "azure": "azure",
        "silero": "silero",
    }
    p = provider.lower()
    for key, val in mapping.items():
        if key in p:
            return val
    return ""


def extract_new_agent(tool_output: str) -> str:
    import re

    m = re.search(r"AgentHandoff\(agent=<(\w+)", tool_output)
    return m.group(1) if m else ""


def coerce_str_sequence(value: AttributeValue | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [text]
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v is not None and str(v).strip()]
        return [text]
    return [str(value)]


def preview_from_chat_ctx(raw: str) -> tuple[str, str]:
    """Return (last_user_text, last_assistant_or_tool_output) from chat_ctx JSON."""
    if not raw:
        return "", ""
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return "", ""
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return "", ""

    last_user = ""
    last_out = ""
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "message":
            role = item.get("role")
            content = item.get("content")
            text = ""
            if isinstance(content, list):
                text = " ".join(str(c) for c in content if c)
            elif content:
                text = str(content)
            if role == "user" and text:
                last_user = text
            elif role == "assistant" and text:
                last_out = text
        elif kind == "function_call_output":
            out = item.get("output", "")
            if out:
                last_out = str(out)
    return last_user, last_out
