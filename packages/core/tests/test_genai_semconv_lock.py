"""Guard GenAI semconv pin + lockfile surface."""

from __future__ import annotations

import json
from pathlib import Path

from parlot.core.attrs import (
    ATTR_GEN_AI_AGENT_ID,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_RESPONSE_MODEL,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOOL_NAME,
    GENAI_SEMCONV_VERSION,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EXECUTE_TOOL,
    GEN_AI_OP_INVOKE_AGENT,
    GEN_AI_OP_INVOKE_WORKFLOW,
    SPAN_GEN_AI_CHAT,
    SPAN_GEN_AI_EXECUTE_TOOL,
    SPAN_GEN_AI_INVOKE_AGENT,
    SPAN_GEN_AI_INVOKE_WORKFLOW,
)

_LOCK = Path(__file__).resolve().parents[1] / "genai_semconv.lock.json"


def test_genai_semconv_lock_matches_attrs() -> None:
    lock = json.loads(_LOCK.read_text())
    assert lock["version"] == GENAI_SEMCONV_VERSION
    assert lock["operations"] == [
        GEN_AI_OP_CHAT,
        GEN_AI_OP_EXECUTE_TOOL,
        GEN_AI_OP_INVOKE_AGENT,
        GEN_AI_OP_INVOKE_WORKFLOW,
    ]
    assert lock["span_bases"] == [
        SPAN_GEN_AI_CHAT,
        SPAN_GEN_AI_EXECUTE_TOOL,
        SPAN_GEN_AI_INVOKE_AGENT,
        SPAN_GEN_AI_INVOKE_WORKFLOW,
    ]
    expected_attrs = {
        ATTR_GEN_AI_OP_NAME,
        ATTR_GEN_AI_MODEL,
        ATTR_GEN_AI_RESPONSE_MODEL,
        ATTR_GEN_AI_PROVIDER,
        ATTR_GEN_AI_SYSTEM,
        ATTR_GEN_AI_IN_TOKENS,
        ATTR_GEN_AI_OUT_TOKENS,
        ATTR_GEN_AI_TOOL_NAME,
        ATTR_GEN_AI_AGENT_ID,
        ATTR_GEN_AI_AGENT_NAME,
        ATTR_GEN_AI_AGENT_VERSION,
        ATTR_GEN_AI_CONVERSATION_ID,
    }
    assert set(lock["attrs"]) == expected_attrs
