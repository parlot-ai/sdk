"""Span name → Parlot agent.role / agent.stage (CONVERSATION_CONTRACT §8)."""

from __future__ import annotations

from parlot.core.attrs import (
    SPAN_AGENT_HANDOFF,
    SPAN_GEN_AI_CHAT,
    SPAN_GEN_AI_EXECUTE_TOOL,
    SPAN_GEN_AI_INVOKE_AGENT,
    SPAN_VOICE_AMD,
    SPAN_VOICE_EOU,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
)
from ._span_rename import native_stage_for_span

# Stages for exported (post-rename) names and remaining contract spans.
_EXPORTED_SPAN_STAGE: dict[str, str] = {
    SPAN_VOICE_STT: "turn",
    SPAN_VOICE_EOU: "eou",
    SPAN_VOICE_TTS: "node",
    SPAN_VOICE_AMD: "classify",
    SPAN_GEN_AI_CHAT: "request",
    SPAN_GEN_AI_EXECUTE_TOOL: "call",
    SPAN_GEN_AI_INVOKE_AGENT: "drain",
    SPAN_AGENT_HANDOFF: "transfer",
}

_EXPORTED_SPAN_ROLE: dict[str, str] = {
    SPAN_VOICE_STT: "stt",
    SPAN_VOICE_EOU: "stt",
    SPAN_VOICE_TTS: "tts",
    SPAN_VOICE_AMD: "amd",
    SPAN_GEN_AI_CHAT: "llm",
    SPAN_GEN_AI_EXECUTE_TOOL: "tool",
    SPAN_GEN_AI_INVOKE_AGENT: "pipeline",
    SPAN_AGENT_HANDOFF: "handoff",
}


def _base_name(span_name: str) -> str:
    if span_name.startswith(f"{SPAN_GEN_AI_CHAT} "):
        return SPAN_GEN_AI_CHAT
    if span_name.startswith(f"{SPAN_GEN_AI_EXECUTE_TOOL} "):
        return SPAN_GEN_AI_EXECUTE_TOOL
    return span_name


def livekit_agent_stage_for_span(span_name: str) -> str | None:
    """Resolve stage from native LiveKit name or exported GenAI/voice name."""
    native = native_stage_for_span(span_name)
    if native:
        return native
    return _EXPORTED_SPAN_STAGE.get(_base_name(span_name))


def livekit_agent_role_for_span(span_name: str) -> str | None:
    """Resolve role for exported GenAI/voice span names."""
    return _EXPORTED_SPAN_ROLE.get(_base_name(span_name))
