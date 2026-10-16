"""Parse Agents 1.8+ GenAI message attributes (input/output.messages)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_GEN_AI_INPUT_MESSAGES,
    ATTR_GEN_AI_OUTPUT_MESSAGES,
    ATTR_GEN_AI_SYSTEM_INSTRUCTIONS,
    ATTR_GEN_AI_TOOL_CALL_ARGUMENTS,
    ATTR_GEN_AI_TOOL_CALL_RESULT,
    GEN_AI_CONTENT_ATTR_KEYS,
)


def _as_str(value: AttributeValue | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return str(value)


def parse_genai_messages(raw: AttributeValue | None) -> list[dict[str, str]]:
    """Parse ``gen_ai.input.messages`` / ``output.messages`` JSON into role/content rows."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        parsed: Any = raw
    else:
        text = _as_str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip().lower()
        if not role:
            continue
        content = ""
        if isinstance(item.get("content"), str):
            content = item["content"]
        elif isinstance(item.get("parts"), list):
            parts: list[str] = []
            for part in item["parts"]:
                if not isinstance(part, Mapping):
                    continue
                if isinstance(part.get("content"), str):
                    parts.append(part["content"])
                elif isinstance(part.get("text"), str):
                    parts.append(part["text"])
            content = "\n".join(p for p in parts if p)
        elif isinstance(item.get("text"), str):
            content = item["text"]
        out.append({"role": role, "content": content})
    return out


def last_message_text(messages: Sequence[Mapping[str, str]], role: str) -> str:
    """Return the last non-empty content for ``role``."""
    want = role.strip().lower()
    for msg in reversed(messages):
        if str(msg.get("role") or "").lower() != want:
            continue
        text = str(msg.get("content") or "").strip()
        if text:
            return text
    return ""


def preview_from_genai_messages(
    attrs: Mapping[str, AttributeValue],
) -> tuple[str, str]:
    """User/assistant text previews from 1.8 message attrs (empty if absent)."""
    input_msgs = parse_genai_messages(attrs.get(ATTR_GEN_AI_INPUT_MESSAGES))
    output_msgs = parse_genai_messages(attrs.get(ATTR_GEN_AI_OUTPUT_MESSAGES))
    user = last_message_text(input_msgs, "user")
    assistant = last_message_text(output_msgs, "assistant") or last_message_text(
        input_msgs, "assistant"
    )
    return user, assistant


def system_instructions_from_attrs(attrs: Mapping[str, AttributeValue]) -> str:
    return str(attrs.get(ATTR_GEN_AI_SYSTEM_INSTRUCTIONS) or "").strip()


def tool_call_payloads_from_attrs(
    attrs: Mapping[str, AttributeValue],
) -> tuple[str, str]:
    """Return (arguments, result) from GenAI tool call attrs when present."""
    args = _as_str(attrs.get(ATTR_GEN_AI_TOOL_CALL_ARGUMENTS)).strip()
    result = _as_str(attrs.get(ATTR_GEN_AI_TOOL_CALL_RESULT)).strip()
    return args, result


def has_genai_message_attrs(attrs: Mapping[str, AttributeValue]) -> bool:
    return bool(
        attrs.get(ATTR_GEN_AI_INPUT_MESSAGES)
        or attrs.get(ATTR_GEN_AI_OUTPUT_MESSAGES)
        or attrs.get(ATTR_GEN_AI_SYSTEM_INSTRUCTIONS)
    )


def genai_content_attr_keys_present(
    attrs: Mapping[str, AttributeValue],
) -> list[str]:
    return [k for k in GEN_AI_CONTENT_ATTR_KEYS if attrs.get(k) is not None]
