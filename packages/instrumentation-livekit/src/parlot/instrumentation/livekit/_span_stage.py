"""LiveKit span name → Parlot agent.role / agent.stage (CONVERSATION_CONTRACT §8)."""

from __future__ import annotations

from parlot.core.attrs import SPAN_AGENT_HANDOFF

_LIVEKIT_SPAN_STAGE: dict[str, str] = {
    "user_turn": "turn",
    "eou_detection": "eou",
    "agent_turn": "turn",
    "drain_agent_activity": "drain",
    "llm_node": "node",
    "llm_request": "request",
    "llm_request_run": "run",
    "tts_node": "node",
    "tts_request_run": "run",
    "function_tool": "call",
    SPAN_AGENT_HANDOFF: "transfer",
    "amd": "classify",
}


def livekit_agent_stage_for_span(span_name: str) -> str | None:
    return _LIVEKIT_SPAN_STAGE.get(span_name)
