"""Tests for GenAI / voice span vocabulary helpers."""

from __future__ import annotations

from parlot.core.attrs import (
    CONTRACT_SPAN_NAMES,
    GENAI_SEMCONV_VERSION,
    SPAN_GEN_AI_CHAT,
    SPAN_GEN_AI_EXECUTE_TOOL,
    SPAN_PARLOT_TURN,
    SPAN_VOICE_TTS,
    is_exportable_span_name,
    is_genai_span_name,
    span_name_chat,
    span_name_execute_tool,
)


def test_genai_semconv_version_pinned() -> None:
    assert GENAI_SEMCONV_VERSION == "1.41.0"


def test_span_name_helpers() -> None:
    assert span_name_chat() == "chat"
    assert span_name_chat("gpt-4o") == "chat gpt-4o"
    assert span_name_execute_tool("lookup") == "execute_tool lookup"
    assert span_name_execute_tool("") == "execute_tool unknown"


def test_is_genai_span_name() -> None:
    assert is_genai_span_name(SPAN_GEN_AI_CHAT)
    assert is_genai_span_name("chat gpt-4o")
    assert is_genai_span_name(SPAN_GEN_AI_EXECUTE_TOOL)
    assert is_genai_span_name("execute_tool lookup")
    assert is_genai_span_name("invoke_agent")
    assert is_genai_span_name("invoke_workflow")
    assert not is_genai_span_name("llm_request")
    assert not is_genai_span_name("function_tool")
    assert not is_genai_span_name(SPAN_PARLOT_TURN)


def test_is_exportable_span_name() -> None:
    for name in CONTRACT_SPAN_NAMES:
        assert is_exportable_span_name(name)
    assert is_exportable_span_name(SPAN_VOICE_TTS)
    assert is_exportable_span_name("chat gpt-4o")
    assert is_exportable_span_name("execute_tool book")
    assert not is_exportable_span_name("user_turn")
    assert not is_exportable_span_name("llm_request")
    assert not is_exportable_span_name("tts_node")
