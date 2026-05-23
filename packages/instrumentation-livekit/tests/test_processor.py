"""Tests for LiveKitGenAIProcessor span enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from parlot.core.attrs import (
    ATTR_AGENT_ROLE,
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_COST_USD,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOOL_DURATION_MS,
    ATTR_GEN_AI_TOOL_IS_HANDOFF,
    ATTR_SESSION_CONTACT_TYPE,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_SESSION_TURN_COUNT,
    ATTR_TURN_INDEX,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_AMD_CATEGORY,
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_LK_USER_TRANSCRIPT,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import get_job_bootstrap
from opentelemetry.sdk.trace import TracerProvider


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


def _bootstrap_proc(proc: LiveKitGenAIProcessor, job_id: str = "job-test") -> MagicMock:
    """Start ``job_entrypoint`` so child spans resolve session via ContextVar."""
    provider = TracerProvider()
    provider.add_span_processor(proc)
    proc.set_tracer(provider.get_tracer("test"))
    entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: job_id})
    proc.on_start(entry)
    return entry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLlmRequestEnrichment:
    def test_cost_computed(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
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
        _bootstrap_proc(proc)
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_PROVIDER: "openai",
            ATTR_GEN_AI_IN_TOKENS: 10,
            ATTR_GEN_AI_OUT_TOKENS: 10,
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_SYSTEM) == "openai"

    def test_cache_hit_rate(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
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
        _bootstrap_proc(proc)
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
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.turn_count = 2

        span = _make_span("llm_node")
        proc.on_end(span)
        assert span._attributes[ATTR_TURN_INDEX] == 2
        assert state.turn_count == 2

    def test_op_name_defaulted(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("llm_node")
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_OP_NAME) == "chat"


class TestFunctionToolEnrichment:
    def test_handoff_auto_detected(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "route",
            ATTR_LK_FNC_TOOL_OUTPUT: "AgentHandoff(agent=<BillingAgent object at 0x1>)",
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_TOOL_IS_HANDOFF) is True

    def test_handoff_explicit_name(self) -> None:
        proc = LiveKitGenAIProcessor(handoff_tool_names={"transfer_to_billing"})
        _bootstrap_proc(proc)
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "transfer_to_billing",
            ATTR_LK_FNC_TOOL_OUTPUT: "ok",
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_TOOL_IS_HANDOFF) is True

    def test_non_handoff_tool(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "get_account_balance",
            ATTR_LK_FNC_TOOL_OUTPUT: "1234.56",
        })
        proc.on_end(span)
        assert ATTR_GEN_AI_TOOL_IS_HANDOFF not in span._attributes

    def test_tool_duration_computed(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("function_tool", start_time=0, end_time=500_000_000)
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_TOOL_DURATION_MS) == pytest.approx(500.0)


class TestRootSpanAggregates:
    def test_session_aggregates_on_conversation_session(self) -> None:
        proc = LiveKitGenAIProcessor()
        job_id = "job-root"
        entry = _bootstrap_proc(proc, job_id)

        proc.on_end(
            _make_span("user_turn", {ATTR_LK_USER_TRANSCRIPT: "hello"}),
        )
        proc.on_end(
            _make_span("agent_turn", {ATTR_LK_AGENT_LABEL: "agent"}),
        )
        assert get_job_bootstrap().state.turn_count == 2
        proc.on_end(entry)

    def test_state_cleaned_up_after_root(self) -> None:
        proc = LiveKitGenAIProcessor()
        entry = _bootstrap_proc(proc, "j1")
        sid = get_job_bootstrap().session_id
        proc.on_end(entry)
        assert sid not in proc._sessions
        assert get_job_bootstrap() is None


class TestContentCapture:
    def test_content_captured_by_default(self) -> None:
        proc = LiveKitGenAIProcessor(capture_content=True)
        _bootstrap_proc(proc, "job-content")
        span = _make_span("agent_turn", {
            ATTR_LK_USER_INPUT: "Hello agent",
            ATTR_LK_RESPONSE_TEXT: "Hi there",
        })
        proc.on_end(span)
        event_names = [e.name for e in span._events]
        assert EVENT_GEN_AI_USER_MESSAGE in event_names
        assert EVENT_GEN_AI_ASSISTANT_MESSAGE in event_names

    def test_content_suppressed_when_disabled(self) -> None:
        proc = LiveKitGenAIProcessor(capture_content=False)
        _bootstrap_proc(proc, "job-content")
        span = _make_span("agent_turn", {
            ATTR_LK_USER_INPUT: "Hello agent",
            ATTR_LK_RESPONSE_TEXT: "Hi there",
        })
        proc.on_end(span)
        assert span._events == []


class TestConversationId:
    def test_gen_ai_conversation_id_stamped(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-conv")
        span = _make_span("llm_node")
        proc.on_end(span)
        session_id = span._attributes[ATTR_SESSION_ID]
        assert span._attributes[ATTR_GEN_AI_CONVERSATION_ID] == session_id
        assert span._attributes[ATTR_SESSION_CONVERSATION_ID] == session_id


class TestAgentIdentity:
    def test_function_tool_stamps_gen_ai_agent_name(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-agent")
        span = _make_span("function_tool", {
            ATTR_LK_AGENT_LABEL: "ReceptionistAgent",
            ATTR_LK_FNC_TOOL_NAME: "lookup",
            ATTR_LK_FNC_TOOL_OUTPUT: "ok",
        })
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "ReceptionistAgent"

    def test_drain_agent_activity_stamps_gen_ai_agent_name_from_state(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-turn")
        state = get_job_bootstrap().state
        state.agent_label = "BillingAgent"
        state.open_agent_turn_index = 1

        span = _make_span("drain_agent_activity")
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "BillingAgent"


class TestAmdEnrichment:
    def test_amd_maps_category_and_role(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-amd")
        span = _make_span("amd", {
            ATTR_AMD_CATEGORY: "machine-vm",
        })
        proc.on_end(span)
        assert span._attributes[ATTR_AGENT_ROLE] == "amd"
        assert span._attributes[ATTR_GEN_AI_OP_NAME] == "classify_contact"
        assert span._attributes[ATTR_SESSION_CONTACT_TYPE] == "voicemail"
        assert span._attributes[ATTR_TURN_INDEX] == 0

    def test_amd_contact_type_on_root(self) -> None:
        proc = LiveKitGenAIProcessor()
        job_id = "job-amd-root"
        entry = _bootstrap_proc(proc, job_id)
        proc.on_end(_make_span("amd", {ATTR_AMD_CATEGORY: "human"}))
        assert get_job_bootstrap().state.contact_type == "human"
        proc.on_end(entry)


class TestHandoffSpanEnrichment:
    def test_lk_agent_handoff_transfer_and_conversation_id(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("lk.agent_handoff", {
            ATTR_AGENT_TRANSFER_FROM: "agent-old",
            ATTR_AGENT_TRANSFER_TO: "agent-new",
        })
        proc.on_end(span)
        assert span._attributes[ATTR_AGENT_TRANSFER_FROM] == "agent-old"
        assert span._attributes[ATTR_AGENT_TRANSFER_TO] == "agent-new"
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "agent-new"
        assert ATTR_GEN_AI_CONVERSATION_ID in span._attributes
        assert ATTR_SESSION_ID in span._attributes
