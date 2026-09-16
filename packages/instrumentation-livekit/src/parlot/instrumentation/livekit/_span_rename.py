"""Remap LiveKit-native pipeline span names to GenAI / voice export names."""

from __future__ import annotations

from typing import Mapping

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_STAGE,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_TOOL_NAME,
    ATTR_PARLOT_SPAN_KIND,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EVALUATE,
    GEN_AI_OP_EXECUTE_TOOL,
    SPAN_GEN_AI_INVOKE_AGENT,
    SPAN_VOICE_AMD,
    SPAN_VOICE_EOU,
    SPAN_VOICE_TTS,
    span_name_chat,
    span_name_execute_tool,
)
from parlot.core.processor import ParlotBaseProcessor
from parlot.instrumentation.livekit.attrs import ATTR_LK_FNC_TOOL_NAME

# Native LiveKit names observed internally by the processor (before rename).
NATIVE_LLM_SPANS = frozenset({"llm_node", "llm_request", "llm_request_run"})
NATIVE_TTS_SPANS = frozenset({"tts_node", "tts_request_run"})
NATIVE_TOOL_SPANS = frozenset({"function_tool"})
NATIVE_TURN_SPANS = frozenset({"user_turn", "agent_turn"})
NATIVE_VOICE_PASSTHROUGH = frozenset({"eou_detection", "amd"})

_NATIVE_STAGE: dict[str, str] = {
    "llm_node": "node",
    "llm_request": "request",
    "llm_request_run": "run",
    "tts_node": "node",
    "tts_request_run": "run",
    "function_tool": "call",
    "eou_detection": "eou",
    "amd": "classify",
}


def native_stage_for_span(span_name: str) -> str | None:
    return _NATIVE_STAGE.get(span_name)


def remap_livekit_span_name(
    native_name: str,
    attrs: Mapping[str, AttributeValue] | None = None,
) -> str | None:
    """Return the export span name for a LiveKit-native span, or None to drop.

    ``user_turn`` / ``agent_turn`` return None (contract ``parlot.turn`` owns turns).
    """
    attrs = attrs or {}
    if native_name in NATIVE_TURN_SPANS:
        return None
    if native_name in NATIVE_LLM_SPANS:
        model = str(attrs.get(ATTR_GEN_AI_MODEL) or "").strip() or None
        return span_name_chat(model)
    if native_name in NATIVE_TOOL_SPANS:
        tool = str(
            attrs.get(ATTR_GEN_AI_TOOL_NAME)
            or attrs.get(ATTR_LK_FNC_TOOL_NAME)
            or ""
        ).strip()
        return span_name_execute_tool(tool)
    if native_name in NATIVE_TTS_SPANS:
        return SPAN_VOICE_TTS
    if native_name == "eou_detection":
        return SPAN_VOICE_EOU
    if native_name == "amd":
        return SPAN_VOICE_AMD
    if native_name == "drain_agent_activity":
        return SPAN_GEN_AI_INVOKE_AGENT
    return native_name


def apply_livekit_span_rename(span: ReadableSpan) -> None:
    """Mutate ``span._name`` and GenAI op attrs for export."""
    native = span.name or ""
    attrs = span.attributes or {}
    exported = remap_livekit_span_name(native, attrs)
    if exported is None:
        return
    if exported != native:
        span._name = exported
    stage = native_stage_for_span(native)
    if stage and not (attrs.get(ATTR_AGENT_STAGE)):
        ParlotBaseProcessor._set(span, ATTR_AGENT_STAGE, stage)
    if native in NATIVE_LLM_SPANS:
        existing_op = str(attrs.get(ATTR_GEN_AI_OP_NAME) or "").strip().lower()
        kind = str(attrs.get(ATTR_PARLOT_SPAN_KIND) or "").strip().lower()
        if existing_op in ("evaluate", "judge") or kind == "evaluation":
            if existing_op not in ("evaluate", "judge"):
                ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EVALUATE)
        else:
            ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_CHAT)
    elif native in NATIVE_TOOL_SPANS:
        ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EXECUTE_TOOL)
        tool = str(
            attrs.get(ATTR_GEN_AI_TOOL_NAME)
            or attrs.get(ATTR_LK_FNC_TOOL_NAME)
            or ""
        ).strip()
        if tool:
            ParlotBaseProcessor._set(span, ATTR_GEN_AI_TOOL_NAME, tool)
