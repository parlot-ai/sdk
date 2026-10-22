"""Remap Pipecat-native pipeline span names to GenAI / voice export names."""

from __future__ import annotations

from typing import Mapping

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_STAGE,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_TOOL_NAME,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EXECUTE_TOOL,
    GEN_AI_OP_GENERATE_CONTENT,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
    span_name_chat,
    span_name_execute_tool,
)
from parlot.core.processor import ParlotBaseProcessor

# Pipecat TurnTraceObserver / service decorator names (and prefixed variants).
NATIVE_CONVERSATION = "conversation"
NATIVE_TURN = "turn"

_NATIVE_STAGE: dict[str, str] = {
    "llm": "request",
    "stt": "request",
    "tts": "request",
    "llm_setup": "setup",
    "llm_response": "response",
    "llm_request": "request",
    "llm_tool_call": "call",
    "llm_tool_result": "result",
}


def _base_service_name(native_name: str) -> str:
    """Normalize ``stt_deepgramsttservice`` / ``llm_openaillmservice`` → family."""
    lower = (native_name or "").strip().lower()
    if not lower:
        return ""
    if lower in (
        "llm",
        "stt",
        "tts",
        "llm_setup",
        "llm_response",
        "llm_request",
        "llm_tool_call",
        "llm_tool_result",
    ):
        return lower
    if lower.startswith("stt"):
        return "stt"
    if lower.startswith("tts"):
        return "tts"
    if lower.startswith("llm_tool"):
        return lower if lower in ("llm_tool_call", "llm_tool_result") else "llm_tool_call"
    if lower.startswith("llm"):
        # llm_setup / llm_response / llm_openaillmservice
        for exact in ("llm_setup", "llm_response", "llm_request", "llm_tool_call", "llm_tool_result"):
            if lower == exact or lower.startswith(exact + "_"):
                return exact
        return "llm"
    return lower


def remap_pipecat_span_name(
    native_name: str,
    attrs: Mapping[str, AttributeValue] | None = None,
) -> str | None:
    """Return the export span name for a Pipecat-native span, or None to drop.

    Native ``conversation`` / ``turn`` return None — the processor mints
    contract ``parlot.session`` / ``parlot.turn`` instead.
    """
    attrs = attrs or {}
    base = _base_service_name(native_name)
    if base in (NATIVE_CONVERSATION, NATIVE_TURN) or native_name in (
        NATIVE_CONVERSATION,
        NATIVE_TURN,
    ):
        return None
    if base in ("llm", "llm_setup", "llm_response", "llm_request"):
        model = str(attrs.get(ATTR_GEN_AI_MODEL) or "").strip() or None
        return span_name_chat(model)
    if base in ("llm_tool_call", "llm_tool_result"):
        tool = str(attrs.get(ATTR_GEN_AI_TOOL_NAME) or "").strip()
        return span_name_execute_tool(tool) if tool else span_name_execute_tool("tool")
    if base == "stt":
        return SPAN_VOICE_STT
    if base == "tts":
        return SPAN_VOICE_TTS
    # Unknown — drop so ExportFilter does not leak vendor names.
    return None


def apply_pipecat_span_rename(span: ReadableSpan) -> None:
    """Mutate ``span._name`` and GenAI op attrs for export."""
    native = span.name or ""
    attrs = span.attributes or {}
    exported = remap_pipecat_span_name(native, attrs)
    if exported is None:
        return
    if exported != native:
        span._name = exported
    base = _base_service_name(native)
    stage = _NATIVE_STAGE.get(base)
    if stage and not attrs.get(ATTR_AGENT_STAGE):
        ParlotBaseProcessor._set(span, ATTR_AGENT_STAGE, stage)
    if base in ("llm", "llm_setup", "llm_response", "llm_request"):
        existing_op = str(attrs.get(ATTR_GEN_AI_OP_NAME) or "").strip().lower()
        if existing_op != GEN_AI_OP_GENERATE_CONTENT:
            ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_CHAT)
    elif base in ("llm_tool_call", "llm_tool_result"):
        ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EXECUTE_TOOL)
