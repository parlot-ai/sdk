"""Tests for LiveKit → GenAI/voice span rename."""

from __future__ import annotations

from parlot.core.attrs import (
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_TOOL_NAME,
    ATTR_PARLOT_SPAN_KIND,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EVALUATE,
    GEN_AI_OP_EXECUTE_TOOL,
    SPAN_VOICE_TTS,
    is_exportable_span_name,
)
from parlot.instrumentation.livekit._span_rename import (
    apply_livekit_span_rename,
    remap_livekit_span_name,
)


class _FakeSpan:
    def __init__(self, name: str, attributes: dict | None = None) -> None:
        self._name = name
        self._attributes = dict(attributes or {})

    @property
    def name(self) -> str:
        return self._name

    @property
    def attributes(self) -> dict:
        return self._attributes


def test_remap_llm_and_tool_names() -> None:
    assert remap_livekit_span_name("llm_request", {ATTR_GEN_AI_MODEL: "gpt-4o"}) == (
        "chat gpt-4o"
    )
    assert remap_livekit_span_name("llm_node", {}) == "chat"
    assert remap_livekit_span_name("function_tool", {"lk.function_tool.name": "book"}) == (
        "execute_tool book"
    )
    assert remap_livekit_span_name("tts_node", {}) == SPAN_VOICE_TTS
    assert remap_livekit_span_name("user_turn", {}) is None
    assert remap_livekit_span_name("agent_turn", {}) is None


def test_apply_rename_mutates_span() -> None:
    span = _FakeSpan("llm_request_run", {ATTR_GEN_AI_MODEL: "gpt-4o-mini"})
    apply_livekit_span_rename(span)  # type: ignore[arg-type]
    assert span.name == "chat gpt-4o-mini"
    assert span.attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_CHAT


def test_apply_rename_preserves_evaluate_op() -> None:
    span = _FakeSpan(
        "llm_request",
        {
            ATTR_GEN_AI_MODEL: "gpt-4.1-mini",
            ATTR_GEN_AI_OP_NAME: GEN_AI_OP_EVALUATE,
            ATTR_PARLOT_SPAN_KIND: "evaluation",
        },
    )
    apply_livekit_span_rename(span)  # type: ignore[arg-type]
    assert span.name == "chat gpt-4.1-mini"
    assert span.attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_EVALUATE


def test_apply_tool_rename() -> None:
    span = _FakeSpan("function_tool", {"lk.function_tool.name": "lookup"})
    apply_livekit_span_rename(span)  # type: ignore[arg-type]
    assert span.name == "execute_tool lookup"
    assert span.attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_EXECUTE_TOOL
    assert span.attributes[ATTR_GEN_AI_TOOL_NAME] == "lookup"


def test_export_allowlist_after_rename() -> None:
    assert is_exportable_span_name("chat gpt-4o")
    assert is_exportable_span_name("execute_tool book")
    assert is_exportable_span_name("tts")
    assert is_exportable_span_name("parlot.turn")
    assert not is_exportable_span_name("user_turn")
    assert not is_exportable_span_name("llm_request")


def test_apply_rename_with_real_otel_bounded_attributes() -> None:
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    span = tracer.start_span("llm_node")
    span.end()

    # On ended span, attributes are immutable BoundedAttributes
    apply_livekit_span_rename(span)
    assert span.name == "chat"
    assert span.attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_CHAT
    assert span.attributes["agent.stage"] == "node"

