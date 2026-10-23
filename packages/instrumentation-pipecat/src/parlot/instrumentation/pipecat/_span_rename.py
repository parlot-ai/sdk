"""Remap Pipecat-native pipeline span names to GenAI / voice export names."""

from __future__ import annotations

from typing import Mapping

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_GEN_AI_OP_NAME,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EXECUTE_TOOL,
    GEN_AI_OP_GENERATE_CONTENT,
)
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.span_rename import apply_genai_span_rename, remap_native_span_name

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

_LLM_BASES = frozenset({"llm", "llm_setup", "llm_response", "llm_request"})
_TOOL_BASES = frozenset({"llm_tool_call", "llm_tool_result"})


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
    return remap_native_span_name(
        base,
        attrs,
        llm_names=_LLM_BASES,
        tool_names=_TOOL_BASES,
        tts_names=("tts",),
        stt_names=("stt",),
        unknown="drop",
    )


def apply_pipecat_span_rename(span: ReadableSpan) -> None:
    """Mutate ``span._name`` and GenAI op attrs for export."""
    native = span.name or ""
    base = _base_service_name(native)

    def _after(
        sp: ReadableSpan,
        _native: str,
        _exported: str,
        attrs: Mapping[str, AttributeValue],
    ) -> None:
        if base in _LLM_BASES:
            existing_op = str(attrs.get(ATTR_GEN_AI_OP_NAME) or "").strip().lower()
            if existing_op != GEN_AI_OP_GENERATE_CONTENT:
                ParlotBaseProcessor._set(sp, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_CHAT)
        elif base in _TOOL_BASES:
            ParlotBaseProcessor._set(sp, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EXECUTE_TOOL)

    apply_genai_span_rename(
        span,
        remap_fn=remap_pipecat_span_name,
        stage_for_native=_NATIVE_STAGE,
        resolve_stage_key=_base_service_name,
        after_rename=_after,
    )
