"""Tests for LiveKitGenAIProcessor span enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 500,
        })
        proc.on_end(span)
        assert "gen_ai.usage.cost_usd" in span._attributes
        assert span._attributes["gen_ai.usage.cost_usd"] > 0

    def test_system_inferred_from_provider(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            "gen_ai.provider.name": "openai",
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 10,
        })
        proc.on_end(span)
        assert span._attributes.get("gen_ai.system") == "openai"

    def test_cache_hit_rate(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 1000,
            "gen_ai.usage.output_tokens": 200,
            "gen_ai.usage.input_cached_tokens": 400,
        })
        proc.on_end(span)
        assert span._attributes.get("gen_ai.usage.cache_hit_rate") == pytest.approx(0.4)

    def test_unknown_model_no_cost(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_request_run", {
            "gen_ai.request.model": "completely-unknown-model",
            "gen_ai.usage.input_tokens": 100,
            "gen_ai.usage.output_tokens": 50,
        })
        proc.on_end(span)
        assert "gen_ai.usage.cost_usd" not in span._attributes


class TestLlmNodeEnrichment:
    def test_turn_index_increments(self) -> None:
        proc = LiveKitGenAIProcessor()
        for expected in range(1, 4):
            span = _make_span("llm_node", {"gen_ai.provider.name": "openai"})
            proc.on_end(span)
            assert span._attributes["lk.turn_index"] == expected

    def test_op_name_defaulted(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("llm_node")
        proc.on_end(span)
        assert span._attributes.get("gen_ai.operation.name") == "chat"


class TestFunctionToolEnrichment:
    def test_handoff_auto_detected(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("function_tool", {
            "lk.function_tool.name": "route",
            "lk.function_tool.output": "AgentHandoff(agent=<BillingAgent object at 0x1>)",
        })
        proc.on_end(span)
        assert span._attributes.get("gen_ai.tool.is_handoff") is True

    def test_handoff_explicit_name(self) -> None:
        proc = LiveKitGenAIProcessor(handoff_tool_names={"transfer_to_billing"})
        span = _make_span("function_tool", {
            "lk.function_tool.name": "transfer_to_billing",
            "lk.function_tool.output": "ok",
        })
        proc.on_end(span)
        assert span._attributes.get("gen_ai.tool.is_handoff") is True

    def test_non_handoff_tool(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("function_tool", {
            "lk.function_tool.name": "get_account_balance",
            "lk.function_tool.output": "1234.56",
        })
        proc.on_end(span)
        assert "gen_ai.tool.is_handoff" not in span._attributes

    def test_tool_duration_computed(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_span("function_tool", start_time=0, end_time=500_000_000)
        proc.on_end(span)
        assert span._attributes.get("gen_ai.tool.duration_ms") == pytest.approx(500.0)


class TestRootSpanAggregates:
    def test_session_aggregates_written(self) -> None:
        proc = LiveKitGenAIProcessor()
        trace_id = 0xCAFEBABE

        def _llm_node():
            s = _make_span("llm_node")
            s.context.trace_id = trace_id
            s.attributes = s._attributes
            return s

        def _root():
            s = _make_span("job_entrypoint", {"lk.job_id": "job-root"})
            s.context.trace_id = trace_id
            s.attributes = s._attributes
            return s

        proc.on_end(_llm_node())
        proc.on_end(_llm_node())
        root = _root()
        proc.on_end(root)

        assert root._attributes["lk.session.turn_count"] == 2

    def test_state_cleaned_up_after_root(self) -> None:
        proc = LiveKitGenAIProcessor()
        trace_id = 0xABCD1234
        root = _make_span("job_entrypoint", {"lk.job_id": "j1"})
        root.context.trace_id = trace_id
        root.attributes = root._attributes
        proc.on_end(root)
        hex_id = format(trace_id, "032x")
        assert hex_id not in proc._sessions


class TestContentCapture:
    def test_content_captured_by_default(self) -> None:
        proc = LiveKitGenAIProcessor(capture_content=True)
        span = _make_span("drain_agent_activity", {
            "lk.user_input": "Hello agent",
            "lk.response.text": "Hi there",
        })
        proc.on_end(span)
        event_names = [e.name for e in span._events]
        assert "gen_ai.user.message" in event_names
        assert "gen_ai.assistant.message" in event_names

    def test_content_suppressed_when_disabled(self) -> None:
        proc = LiveKitGenAIProcessor(capture_content=False)
        span = _make_span("drain_agent_activity", {
            "lk.user_input": "Hello agent",
            "lk.response.text": "Hi there",
        })
        proc.on_end(span)
        assert span._events == []
