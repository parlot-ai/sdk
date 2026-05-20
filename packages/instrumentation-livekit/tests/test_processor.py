"""Tests for LiveKitGenAIProcessor span enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from parlot.core.attrs import (
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
    ATTR_GEN_AI_COST_USD,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOOL_DURATION_MS,
    ATTR_GEN_AI_TOOL_IS_HANDOFF,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_SESSION_TURNS,
    ATTR_LK_TURN_INDEX,
    ATTR_LK_USER_INPUT,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor


# ---------------------------------------------------------------------------
# Minimal ReadableSpan stub
# ---------------------------------------------------------------------------

def _make_span(name: str, attributes: dict | None = None,
               start_time: int = 1_000_000_000,
               end_time: int   = 2_000_000_000) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = start_time
    span.end_time   = end_time
    span.context.trace_id = 0xDEADBEEF
    span.attributes = span._attributes
    return span


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLlmRequestEnrichment:
    def test_cost_computed(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_MODEL: "gpt-4o",
            ATTR_GEN_AI_IN_TOKENS: 1000,
            ATTR_GEN_AI_OUT_TOKENS: 500,
        })
        proc.on_end(span)
        assert ATTR_GEN_AI_COST_USD in span._attributes
        assert span._attributes[ATTR_GEN_AI_COST_USD] > 0

    def test_system_inferred_from_provider(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_PROVIDER: "openai",
            ATTR_GEN_AI_IN_TOKENS: 10,
            ATTR_GEN_AI_OUT_TOKENS: 10,
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_SYSTEM) == "openai"

    def test_cache_hit_rate(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_MODEL: "gpt-4o",
            ATTR_GEN_AI_IN_TOKENS: 1000,
            ATTR_GEN_AI_OUT_TOKENS: 200,
            ATTR_GEN_AI_CACHED_TOKENS: 400,
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_CACHE_HIT_RATE) == pytest.approx(0.4)

    def test_unknown_model_no_cost(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_MODEL: "completely-unknown-model",
            ATTR_GEN_AI_IN_TOKENS: 100,
            ATTR_GEN_AI_OUT_TOKENS: 50,
        })
        proc.on_end(span)
        assert ATTR_GEN_AI_COST_USD not in span._attributes


class TestLlmNodeEnrichment:
    def test_turn_index_stamped_not_incremented(self) -> None:
        proc = LiveKitGenAIProcessor()
        from parlot.instrumentation.livekit._processor import _LiveKitSessionState

        proc._sessions["job-llm"] = _LiveKitSessionState()
        state = proc._sessions["job-llm"]
        state.parlot_session_id = "f" * 32
        state.turn_count = 2

        span = _make_span("llm_node", {ATTR_LK_JOB_ID: "job-llm"})
        proc.on_end(span)
        assert span._attributes[ATTR_LK_TURN_INDEX] == 2
        assert state.turn_count == 2

    def test_op_name_defaulted(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_node")
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_OP_NAME) == "chat"


class TestFunctionToolEnrichment:
    def test_handoff_auto_detected(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "route",
            ATTR_LK_FNC_TOOL_OUTPUT: "AgentHandoff(agent=<BillingAgent object at 0x1>)",
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_TOOL_IS_HANDOFF) is True

    def test_handoff_explicit_name(self) -> None:
        proc = LiveKitGenAIProcessor(handoff_tool_names={"transfer_to_billing"})
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "transfer_to_billing",
            ATTR_LK_FNC_TOOL_OUTPUT: "ok",
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_TOOL_IS_HANDOFF) is True

    def test_non_handoff_tool(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "get_account_balance",
            ATTR_LK_FNC_TOOL_OUTPUT: "1234.56",
        })
        proc.on_end(span)
        assert ATTR_GEN_AI_TOOL_IS_HANDOFF not in span._attributes

    def test_tool_duration_computed(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("function_tool", start_time=0, end_time=500_000_000)
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_TOOL_DURATION_MS) == pytest.approx(500.0)


class TestRootSpanAggregates:
    def test_session_aggregates_written(self) -> None:
        proc = LiveKitGenAIProcessor()
        job_id = "job-root"

        proc.on_end(_make_span("eou_detection", {ATTR_LK_JOB_ID: job_id}))
        proc.on_end(_make_span("drain_agent_activity", {ATTR_LK_JOB_ID: job_id}))
        root = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: job_id})
        proc.on_end(root)

        assert root._attributes[ATTR_LK_SESSION_TURNS] == 2

    def test_state_cleaned_up_after_root(self) -> None:
        proc = LiveKitGenAIProcessor()
        trace_id = 0xABCD1234
        root = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "j1"})
        root.context.trace_id = trace_id
        root.attributes = root._attributes
        proc.on_end(root)
        hex_id = format(trace_id, "032x")
        assert hex_id not in proc._sessions


class TestContentCapture:
    def test_content_captured_by_default(self) -> None:
        proc = LiveKitGenAIProcessor(capture_content=True)
        span = _make_span("drain_agent_activity", {
            ATTR_LK_USER_INPUT: "Hello agent",
            ATTR_LK_RESPONSE_TEXT: "Hi there",
        })
        proc.on_end(span)
        event_names = [e.name for e in span._events]
        assert EVENT_GEN_AI_USER_MESSAGE in event_names
        assert EVENT_GEN_AI_ASSISTANT_MESSAGE in event_names

    def test_content_suppressed_when_disabled(self) -> None:
        proc = LiveKitGenAIProcessor(capture_content=False)
        span = _make_span("drain_agent_activity", {
            ATTR_LK_USER_INPUT: "Hello agent",
            ATTR_LK_RESPONSE_TEXT: "Hi there",
        })
        proc.on_end(span)
        assert span._events == []
