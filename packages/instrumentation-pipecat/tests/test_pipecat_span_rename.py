"""Unit tests for Pipecat span name remapping."""

from __future__ import annotations

from parlot.core.attrs import (
    ATTR_GEN_AI_MODEL,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
    span_name_chat,
)
from parlot.instrumentation.pipecat._span_rename import remap_pipecat_span_name


def test_drops_conversation_and_turn() -> None:
    assert remap_pipecat_span_name("conversation") is None
    assert remap_pipecat_span_name("turn") is None


def test_remaps_service_families() -> None:
    assert remap_pipecat_span_name("stt_deepgramsttservice") == SPAN_VOICE_STT
    assert remap_pipecat_span_name("tts_cartesiattsservice") == SPAN_VOICE_TTS
    assert remap_pipecat_span_name(
        "llm_openaillmservice",
        {ATTR_GEN_AI_MODEL: "gpt-4o"},
    ) == span_name_chat("gpt-4o")
    assert remap_pipecat_span_name("llm") == span_name_chat(None)


def test_drops_unknown() -> None:
    assert remap_pipecat_span_name("user_speaking") is None
    assert remap_pipecat_span_name("StartFrame") is None
