"""Remap LiveKit-native pipeline span names to GenAI / voice export names."""

from __future__ import annotations

from typing import Mapping

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_TOOL_NAME,
    ATTR_PARLOT_SPAN_KIND,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EXECUTE_TOOL,
    GEN_AI_OP_GENERATE_CONTENT,
    PARLOT_EVAL_OP_EVALUATE,
    PARLOT_EVAL_OP_JUDGE,
    PARLOT_SPAN_KIND_EVALUATION,
    SPAN_GEN_AI_INVOKE_AGENT,
    SPAN_VOICE_AMD,
    SPAN_VOICE_EOU,
)
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.span_rename import apply_genai_span_rename, remap_native_span_name
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_FNC_TOOL_NAME,
    NATIVE_SPAN_REALTIME_INFERENCE,
    NATIVE_SPAN_REALTIME_METRICS,
)

# Native LiveKit names observed internally by the processor (before rename).
NATIVE_LLM_SPANS = frozenset({"llm_node", "llm_request", "llm_request_run"})
NATIVE_REALTIME_SPANS = frozenset(
    {NATIVE_SPAN_REALTIME_INFERENCE, NATIVE_SPAN_REALTIME_METRICS}
)
NATIVE_TTS_SPANS = frozenset({"tts_node", "tts_request_run"})
NATIVE_TOOL_SPANS = frozenset({"function_tool"})
NATIVE_TURN_SPANS = frozenset({"user_turn", "agent_turn"})
NATIVE_VOICE_PASSTHROUGH = frozenset({"eou_detection", "amd"})

_NATIVE_STAGE: dict[str, str] = {
    "llm_node": "node",
    "llm_request": "request",
    "llm_request_run": "run",
    NATIVE_SPAN_REALTIME_INFERENCE: "request",
    NATIVE_SPAN_REALTIME_METRICS: "request",
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

    def _custom(
        name: str, _attrs: Mapping[str, AttributeValue]
    ) -> str | None | object:
        if name == NATIVE_SPAN_REALTIME_METRICS:
            # Late usage sibling — keep for enrich/merge; drop from export name path
            # by returning None after tokens are applied (see processor).
            return None
        if name == NATIVE_SPAN_REALTIME_INFERENCE:
            return NotImplemented  # fall through as LLM
        if name == "eou_detection":
            return SPAN_VOICE_EOU
        if name == "amd":
            return SPAN_VOICE_AMD
        if name == "drain_agent_activity":
            return SPAN_GEN_AI_INVOKE_AGENT
        return NotImplemented

    llm_names = frozenset(NATIVE_LLM_SPANS | {NATIVE_SPAN_REALTIME_INFERENCE})
    return remap_native_span_name(
        native_name,
        attrs,
        llm_names=llm_names,
        tool_names=NATIVE_TOOL_SPANS,
        tts_names=NATIVE_TTS_SPANS,
        drop_names=NATIVE_TURN_SPANS,
        tool_name_attrs=(ATTR_GEN_AI_TOOL_NAME, ATTR_LK_FNC_TOOL_NAME),
        unknown="passthrough",
        custom=_custom,
    )


def apply_livekit_span_rename(span: ReadableSpan) -> None:
    """Mutate ``span._name`` and GenAI op attrs for export."""

    def _after(
        sp: ReadableSpan,
        native: str,
        _exported: str,
        attrs: Mapping[str, AttributeValue],
    ) -> None:
        if native == NATIVE_SPAN_REALTIME_INFERENCE:
            existing_op = str(attrs.get(ATTR_GEN_AI_OP_NAME) or "").strip().lower()
            kind = str(attrs.get(ATTR_PARLOT_SPAN_KIND) or "").strip().lower()
            if (
                existing_op in (PARLOT_EVAL_OP_EVALUATE, PARLOT_EVAL_OP_JUDGE)
                or kind == PARLOT_SPAN_KIND_EVALUATION
            ):
                pass
            elif existing_op and existing_op != GEN_AI_OP_CHAT:
                # Preserve generate_content (and any other non-chat op LiveKit set).
                pass
            else:
                ParlotBaseProcessor._set(
                    sp, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_GENERATE_CONTENT
                )
        elif native in NATIVE_LLM_SPANS:
            existing_op = str(attrs.get(ATTR_GEN_AI_OP_NAME) or "").strip().lower()
            kind = str(attrs.get(ATTR_PARLOT_SPAN_KIND) or "").strip().lower()
            # Do not invent GenAI ops for evaluation; leave vendor/legacy op alone
            # and rely on parlot.span.kind=evaluation.
            if (
                existing_op in (PARLOT_EVAL_OP_EVALUATE, PARLOT_EVAL_OP_JUDGE)
                or kind == PARLOT_SPAN_KIND_EVALUATION
            ):
                pass
            elif existing_op == GEN_AI_OP_GENERATE_CONTENT:
                pass
            else:
                ParlotBaseProcessor._set(sp, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_CHAT)
        elif native in NATIVE_TOOL_SPANS:
            ParlotBaseProcessor._set(sp, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EXECUTE_TOOL)
            tool = str(
                attrs.get(ATTR_GEN_AI_TOOL_NAME)
                or attrs.get(ATTR_LK_FNC_TOOL_NAME)
                or ""
            ).strip()
            if tool:
                ParlotBaseProcessor._set(sp, ATTR_GEN_AI_TOOL_NAME, tool)

    apply_genai_span_rename(
        span,
        remap_fn=remap_livekit_span_name,
        stage_for_native=_NATIVE_STAGE,
        after_rename=_after,
    )
