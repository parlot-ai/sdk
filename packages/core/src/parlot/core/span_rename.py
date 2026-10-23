"""Table-driven GenAI / voice span rename helpers for instrumentation adapters."""

from __future__ import annotations

from collections.abc import Collection
from typing import Callable, Literal, Mapping

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

UnknownPolicy = Literal["drop", "passthrough"]


def remap_native_span_name(
    native: str,
    attrs: Mapping[str, AttributeValue] | None = None,
    *,
    llm_names: Collection[str] = (),
    tool_names: Collection[str] = (),
    tts_names: Collection[str] = (),
    stt_names: Collection[str] = (),
    drop_names: Collection[str] = (),
    tool_name_attrs: Collection[str] = (ATTR_GEN_AI_TOOL_NAME,),
    unknown: UnknownPolicy = "drop",
    custom: Callable[
        [str, Mapping[str, AttributeValue]], str | None | object
    ]
    | None = None,
) -> str | None:
    """Map a vendor-native span name to a GenAI / voice export name.

    Returns ``None`` to drop the span from the export name path.

    ``custom`` may return a string, ``None`` (drop), or the sentinel
    ``NotImplemented`` to fall through to the table-driven rules.
    """
    attrs = attrs or {}
    native_name = native or ""

    if custom is not None:
        result = custom(native_name, attrs)
        if result is not NotImplemented:
            return result  # type: ignore[return-value]

    if native_name in drop_names:
        return None
    if native_name in llm_names:
        model = str(attrs.get(ATTR_GEN_AI_MODEL) or "").strip() or None
        return span_name_chat(model)
    if native_name in tool_names:
        tool = ""
        for key in tool_name_attrs:
            tool = str(attrs.get(key) or "").strip()
            if tool:
                break
        return span_name_execute_tool(tool)
    if native_name in tts_names:
        return SPAN_VOICE_TTS
    if native_name in stt_names:
        return SPAN_VOICE_STT
    if unknown == "passthrough":
        return native_name
    return None


def apply_genai_span_rename(
    span: ReadableSpan,
    *,
    remap_fn: Callable[[str, Mapping[str, AttributeValue] | None], str | None],
    stage_for_native: Mapping[str, str] | None = None,
    llm_names: Collection[str] = (),
    tool_names: Collection[str] = (),
    set_chat_op: bool = True,
    set_tool_op: bool = True,
    preserve_ops: frozenset[str] | None = None,
    resolve_stage_key: Callable[[str], str] | None = None,
    after_rename: Callable[
        [ReadableSpan, str, str, Mapping[str, AttributeValue]], None
    ]
    | None = None,
) -> None:
    """Mutate ``span._name`` and GenAI op / stage attrs for export.

    ``after_rename(span, native, exported, attrs)`` runs when the adapter needs
    extra logic (e.g. LiveKit evaluation op preservation, tool name sync).
    When provided, it replaces the default chat/tool op stamping.
    """
    native = span.name or ""
    attrs = span.attributes or {}
    exported = remap_fn(native, attrs)
    if exported is None:
        return
    if exported != native:
        span._name = exported  # type: ignore[attr-defined]

    stage_key = resolve_stage_key(native) if resolve_stage_key else native
    if stage_for_native:
        stage = stage_for_native.get(stage_key)
        if stage and not attrs.get(ATTR_AGENT_STAGE):
            ParlotBaseProcessor._set(span, ATTR_AGENT_STAGE, stage)

    if after_rename is not None:
        after_rename(span, native, exported, attrs)
        return

    preserve = preserve_ops or frozenset({GEN_AI_OP_GENERATE_CONTENT})
    if set_chat_op and native in llm_names:
        existing_op = str(attrs.get(ATTR_GEN_AI_OP_NAME) or "").strip().lower()
        if existing_op not in preserve:
            ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_CHAT)
    elif set_tool_op and native in tool_names:
        ParlotBaseProcessor._set(span, ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EXECUTE_TOOL)
