"""Tests for LiveKitGenAIProcessor span enrichment."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from parlot.core.attrs import (
    SPAN_AGENT_HANDOFF,
    ATTR_AGENT_INSTRUCTIONS_EXCERPT,
    ATTR_AGENT_STATIC_INSTRUCTIONS_EXCERPT,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_AGENT_TOOL_TIMING_CORRECTED,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_RESPONSE_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOOL_DURATION_MS,
    ATTR_GEN_AI_TOOL_IS_HANDOFF,
    ATTR_PARLOT_SPAN_KIND,
    ATTR_SESSION_AMD,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_USER_TEXT,
    ATTR_EXCEPTION_TYPE,
    ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
    PARLOT_SPAN_KIND_EVALUATION,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_AMD_CATEGORY,
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_AGENT_NAME,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_FNC_TOOL_ERROR,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_INSTRUCTIONS,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_LK_USER_TRANSCRIPT,
)
from opentelemetry.trace import StatusCode
from parlot.core.processor import assert_sync_span_processors
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import (
    clear_all_sticky_closed_sessions,
    finalize_session_close_from_hook,
    get_job_bootstrap,
    get_sticky_closed_session,
)
from opentelemetry.sdk.trace import TracerProvider
from bootstrap_helpers import bootstrap_via_agent_state


# ---------------------------------------------------------------------------
# Minimal ReadableSpan stub
# ---------------------------------------------------------------------------

class _SpanStub:
    """ReadableSpan stand-in; mirrors OTel's private _start_time/_end_time fields."""

    def __init__(
        self,
        name: str,
        attributes: dict | None = None,
        *,
        start_time: int = 1_000_000_000,
        end_time: int = 2_000_000_000,
    ) -> None:
        self.name = name
        self._attributes = dict(attributes or {})
        self._events: list = []
        self._start_time = start_time
        self._end_time = end_time
        self.context = SimpleNamespace(trace_id=0xDEADBEEF, span_id=0xBEEF)

    @property
    def attributes(self):
        return self._attributes

    @property
    def start_time(self) -> int:
        return self._start_time

    @property
    def end_time(self) -> int:
        return self._end_time

    def set_attribute(self, key: str, value) -> None:
        self._attributes[key] = value


def _make_span(
    name: str,
    attributes: dict | None = None,
    start_time: int = 1_000_000_000,
    end_time: int = 2_000_000_000,
) -> _SpanStub:
    return _SpanStub(
        name,
        attributes,
        start_time=start_time,
        end_time=end_time,
    )


def _bootstrap_proc(proc: LiveKitGenAIProcessor, job_id: str = "job-test") -> None:
    """Bootstrap via agent_state_changed so child spans resolve session via ContextVar."""
    provider = TracerProvider()
    provider.add_span_processor(proc)
    assert_sync_span_processors(provider)
    proc.set_tracer(provider.get_tracer("test"))
    bootstrap_via_agent_state(proc, job_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLlmRequestEnrichment:
    def test_token_counts_accumulated(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_MODEL: "gpt-4o",
            ATTR_GEN_AI_IN_TOKENS: 1000,
            ATTR_GEN_AI_OUT_TOKENS: 500,
        })
        proc.on_end(span)
        state = get_job_bootstrap().state
        assert state.total_input_tokens == 1000
        assert state.total_output_tokens == 500

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

    def test_llm_request_stamps_agent_identity(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.agent_label = "greeter"

        span = _make_span("llm_request", {
            ATTR_GEN_AI_MODEL: "gpt-4o",
            ATTR_GEN_AI_IN_TOKENS: 10,
            ATTR_GEN_AI_OUT_TOKENS: 5,
        })
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "greeter"

    def test_distinct_response_model_preserved(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_MODEL: "gpt-4o",
            ATTR_GEN_AI_RESPONSE_MODEL: "gpt-4o-2024-08-06",
            ATTR_GEN_AI_IN_TOKENS: 10,
            ATTR_GEN_AI_OUT_TOKENS: 5,
        })
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_RESPONSE_MODEL) == "gpt-4o-2024-08-06"

    def test_matching_response_model_not_stamped(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("llm_request_run", {
            ATTR_GEN_AI_MODEL: "gpt-4o",
            ATTR_GEN_AI_IN_TOKENS: 10,
            ATTR_GEN_AI_OUT_TOKENS: 5,
        })
        proc.on_end(span)
        assert ATTR_GEN_AI_RESPONSE_MODEL not in span._attributes

    def test_exception_sets_error_status(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("llm_request_run", {ATTR_EXCEPTION_TYPE: "APIStatusError"})
        proc.on_end(span)
        assert span._status.status_code == StatusCode.ERROR

    def test_tool_error_sets_error_status(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("function_tool", {
            ATTR_LK_FNC_TOOL_NAME: "book_appointment",
            ATTR_LK_FNC_TOOL_ERROR: True,
            ATTR_LK_FNC_TOOL_OUTPUT: "AgentTask get_email_task is cancelled",
        })
        proc.on_end(span)
        assert span._status.status_code == StatusCode.ERROR
        assert span._attributes.get(ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW) == (
            "AgentTask get_email_task is cancelled"
        )


class TestLlmNodeEnrichment:
    def test_turn_index_stamped_not_incremented(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.turn_count = 2

        span = _make_span("llm_node")
        proc.on_end(span)
        # Open agent turn is turn_count+1 (same as commit_agent_message).
        assert span._attributes[ATTR_TURN_INDEX] == 3
        assert state.turn_count == 2

    def test_op_name_defaulted(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span("llm_node")
        proc.on_end(span)
        assert span._attributes.get(ATTR_GEN_AI_OP_NAME) == "chat"

    def test_chat_ctx_user_message_preserved_after_function_call(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        chat_ctx = json.dumps({
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "book me tomorrow",
                },
                {
                    "type": "function_call",
                    "name": "book_appointment",
                    "arguments": '{"date": "tomorrow"}',
                },
            ],
        })
        span = _make_span("llm_node", {ATTR_LK_CHAT_CTX: chat_ctx})
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "book me tomorrow"

    def test_chat_ctx_function_call_only_does_not_set_user_text(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        chat_ctx = json.dumps({
            "items": [
                {
                    "type": "function_call",
                    "name": "book_appointment",
                    "arguments": '{"date": "tomorrow"}',
                },
            ],
        })
        span = _make_span("llm_node", {ATTR_LK_CHAT_CTX: chat_ctx})
        proc.on_end(span)
        assert ATTR_TURN_USER_TEXT not in span._attributes

    def test_chat_ctx_string_arg_function_call_preserves_user_message(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        chat_ctx = json.dumps({
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "lookup tomorrow",
                },
                {
                    "type": "function_call",
                    "name": "lookup",
                    "arguments": '"tomorrow"',
                },
            ],
        })
        span = _make_span("llm_node", {ATTR_LK_CHAT_CTX: chat_ctx})
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "lookup tomorrow"

    def test_llm_node_stamps_agent_identity_and_topology_instructions(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.agent_label = "greeter"

        span = _make_span(
            "llm_node",
            {ATTR_LK_INSTRUCTIONS: "You are a friendly restaurant receptionist."},
        )
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "greeter"
        assert "restaurant receptionist" in span._attributes[ATTR_AGENT_INSTRUCTIONS_EXCERPT]
        assert "restaurant receptionist" in span._attributes[ATTR_AGENT_STATIC_INSTRUCTIONS_EXCERPT]
        assert state.topology.prompts_by_agent["greeter"].startswith(
            "You are a friendly restaurant receptionist."
        )

    def test_llm_node_stamps_gen_ai_agent_name_from_lk_agent_label(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-llm-label")

        span = _make_span(
            "llm_node",
            {
                ATTR_LK_AGENT_LABEL: "reservation",
                ATTR_LK_INSTRUCTIONS: "You are Reservation agent.",
            },
        )
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "reservation"

    def test_llm_node_splits_static_and_full_instruction_excerpts(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.agent_label = "greeter"

        static_config = "You are a friendly restaurant receptionist."
        runtime = "You are Greeter agent. Current user data is checked_out: false"
        chat_ctx = json.dumps({
            "items": [
                {"type": "agent_config_update", "instructions": static_config},
                {"type": "message", "role": "system", "content": [runtime]},
            ],
        })
        span = _make_span("llm_node", {ATTR_LK_CHAT_CTX: chat_ctx})
        proc.on_end(span)

        full = span._attributes[ATTR_AGENT_INSTRUCTIONS_EXCERPT]
        static = span._attributes[ATTR_AGENT_STATIC_INSTRUCTIONS_EXCERPT]
        assert static_config in full
        assert "Current user data" in full
        assert static_config in static
        assert "Current user data" not in static
        assert state.topology.prompts_by_agent["greeter"] == static_config


class TestEventsModeTurnText:
    def test_llm_node_skips_user_text_in_events_mode(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        proc.set_turn_source("events")
        chat_ctx = json.dumps({
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": "book me tomorrow",
                },
            ],
        })
        span = _make_span("llm_node", {ATTR_LK_CHAT_CTX: chat_ctx})
        proc.on_end(span)
        assert ATTR_TURN_USER_TEXT not in span._attributes

    def test_llm_node_skips_agent_text_in_events_mode(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        proc.set_turn_source("events")
        chat_ctx = json.dumps({
            "items": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "stale prior turn reply",
                },
            ],
        })
        span = _make_span("llm_node", {ATTR_LK_CHAT_CTX: chat_ctx})
        proc.on_end(span)
        assert ATTR_TURN_AGENT_TEXT not in span._attributes

    def test_user_turn_stamps_committed_text_in_events_mode(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        proc.set_turn_source("events")
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        bootstrap.state.turn_count = 1
        bootstrap.state.user_text_by_turn[1] = "Committed user line"

        span = _make_span(
            "user_turn",
            {
                ATTR_LK_JOB_ID: "job-test",
                ATTR_LK_USER_TRANSCRIPT: "stale transcript",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "Committed user line"


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


class TestFunctionToolExportTiming:
    def test_corrects_async_tool_span_start_at_export(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        executed_ns = 120_000_000_000
        get_job_bootstrap().state.tool_execution_ns_queue.append(executed_ns)

        span = _make_span(
            "function_tool",
            {
                ATTR_LK_FNC_TOOL_NAME: "book_appointment",
                ATTR_LK_FNC_TOOL_ERROR: True,
            },
            start_time=8_000_000_000,
            end_time=125_000_000_000,
        )
        proc.enrich_spans_for_export([span])
        assert span.start_time == executed_ns
        assert span._attributes.get(ATTR_AGENT_TOOL_TIMING_CORRECTED) is True
        assert span._attributes.get(ATTR_GEN_AI_TOOL_DURATION_MS) == pytest.approx(
            5000.0,
        )

    def test_leaves_short_tool_spans_unchanged(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        get_job_bootstrap().state.tool_execution_ns_queue.append(1_050_000_000)

        span = _make_span(
            "function_tool",
            {ATTR_LK_FNC_TOOL_NAME: "check_slots"},
            start_time=1_000_000_000,
            end_time=2_000_000_000,
        )
        original_start = span.start_time
        proc.enrich_spans_for_export([span])
        assert span.start_time == original_start
        assert ATTR_AGENT_TOOL_TIMING_CORRECTED not in span._attributes


class TestRootSpanAggregates:
    def test_session_aggregates_on_conversation_session(self) -> None:
        proc = LiveKitGenAIProcessor()
        job_id = "job-root"
        _bootstrap_proc(proc, job_id)

        proc.on_end(
            _make_span("user_turn", {ATTR_LK_USER_TRANSCRIPT: "hello"}),
        )
        proc.on_end(
            _make_span("agent_turn", {ATTR_LK_AGENT_LABEL: "agent"}),
        )
        assert get_job_bootstrap().state.turn_count == 2

    def test_state_cleaned_up_after_root(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "j1")
        bootstrap = get_job_bootstrap()
        sid = bootstrap.session_id
        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")
        assert sid not in proc._sessions
        assert get_job_bootstrap() is None

    def test_late_agent_turn_after_close_logs_debug_not_error(self, caplog: pytest.LogCaptureFixture) -> None:
        proc = LiveKitGenAIProcessor()
        job_id = "AJ_late"
        _bootstrap_proc(proc, job_id)
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        finalize_session_close_from_hook(
            bootstrap,
            close_reason="participant_disconnected",
        )
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="parlot.instrumentation.livekit"):
            proc.on_end(
                _make_span(
                    "agent_turn",
                    {
                        ATTR_LK_JOB_ID: job_id,
                        ATTR_LK_USER_INPUT: "Hello?",
                    },
                ),
            )
        bootstrap_msgs = [r for r in caplog.records if "no session bootstrap" in r.message]
        assert bootstrap_msgs
        assert all(r.levelno == logging.DEBUG for r in bootstrap_msgs)
        assert not any(r.levelno >= logging.ERROR for r in bootstrap_msgs)

    def test_late_llm_after_close_uses_sticky_session_as_evaluation(self) -> None:
        clear_all_sticky_closed_sessions()
        proc = LiveKitGenAIProcessor()
        job_id = "AJ_sticky_eval"
        _bootstrap_proc(proc, job_id)
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        closed_sid = bootstrap.session_id
        turn_count_before = bootstrap.state.turn_count
        tokens_before = bootstrap.state.total_input_tokens
        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")
        sticky = get_sticky_closed_session(job_id)
        assert sticky is not None
        assert sticky.session_id == closed_sid

        span = _make_span(
            "llm_request",
            {
                ATTR_LK_JOB_ID: job_id,
                ATTR_GEN_AI_MODEL: "gpt-4.1-mini",
                ATTR_GEN_AI_IN_TOKENS: 10,
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_SESSION_ID) == closed_sid
        assert span._attributes.get(ATTR_PARLOT_SPAN_KIND) == PARLOT_SPAN_KIND_EVALUATION
        # Evaluation uses Layer-3 parlot.span.kind — do not invent a GenAI op.
        assert span._attributes.get(ATTR_GEN_AI_OP_NAME) != "evaluate"
        # Must not mutate closed session aggregates via sticky path.
        assert get_job_bootstrap() is None
        assert turn_count_before == 0
        assert tokens_before == 0

    def test_new_bootstrap_clears_sticky_and_does_not_leak_prior_session(self) -> None:
        clear_all_sticky_closed_sessions()
        proc = LiveKitGenAIProcessor()
        job_id = "AJ_sticky_isolation"
        _bootstrap_proc(proc, job_id)
        bootstrap_a = get_job_bootstrap()
        assert bootstrap_a is not None
        sid_a = bootstrap_a.session_id
        finalize_session_close_from_hook(bootstrap_a, close_reason="clean_close")
        assert get_sticky_closed_session(job_id) is not None
        assert get_sticky_closed_session(job_id).session_id == sid_a

        _bootstrap_proc(proc, job_id)
        bootstrap_b = get_job_bootstrap()
        assert bootstrap_b is not None
        sid_b = bootstrap_b.session_id
        assert sid_b != sid_a
        assert get_sticky_closed_session(job_id) is None

        span = _make_span(
            "llm_request",
            {ATTR_LK_JOB_ID: job_id, ATTR_GEN_AI_MODEL: "gpt-4o"},
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_SESSION_ID) == sid_b
        assert span._attributes.get(ATTR_PARLOT_SPAN_KIND) is None

    def test_active_bootstrap_ignores_leftover_sticky(self) -> None:
        clear_all_sticky_closed_sessions()
        proc = LiveKitGenAIProcessor()
        job_id = "AJ_sticky_active"
        _bootstrap_proc(proc, job_id)
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        sid_a = bootstrap.session_id
        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")

        # Simulate sticky still present while a new session is active (should not happen
        # after clear-on-bootstrap, but active bootstrap must win).
        from parlot.instrumentation.livekit._session import remember_sticky_closed_session

        _bootstrap_proc(proc, job_id)
        bootstrap_b = get_job_bootstrap()
        assert bootstrap_b is not None
        sid_b = bootstrap_b.session_id
        remember_sticky_closed_session(
            job_id, session_id=sid_a, conversation_id=sid_a
        )
        span = _make_span(
            "llm_request",
            {ATTR_LK_JOB_ID: job_id, ATTR_GEN_AI_MODEL: "gpt-4o"},
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_SESSION_ID) == sid_b
        assert span._attributes.get(ATTR_PARLOT_SPAN_KIND) is None


class TestGenAIContentCapture:
    def test_genai_content_captured_by_default(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
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
        proc = LiveKitGenAIProcessor(capture_genai_content=False)
        _bootstrap_proc(proc, "job-content")
        span = _make_span("agent_turn", {
            ATTR_LK_USER_INPUT: "Hello agent",
            ATTR_LK_RESPONSE_TEXT: "Hi there",
        })
        proc.on_end(span)
        assert span._events == []
        # Contract turn text remains for debugger/evals.
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "Hello agent"
        assert span._attributes.get(ATTR_TURN_AGENT_TEXT) == "Hi there"


class TestTurnTextExport:
    def test_user_turn_exports_full_transcript_without_sdk_cap(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-long-text")
        long_text = "word " * 300
        span = _make_span("user_turn", {ATTR_LK_USER_TRANSCRIPT: long_text})
        proc.on_end(span)
        exported = span._attributes.get(ATTR_TURN_USER_TEXT)
        assert exported == long_text.strip()
        assert len(exported) > 512

    def test_agent_turn_exports_full_response_text(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-long-response")
        long_response = "reply " * 300
        span = _make_span("agent_turn", {
            ATTR_LK_USER_INPUT: "short prompt",
            ATTR_LK_RESPONSE_TEXT: long_response,
        })
        proc.on_end(span)
        exported = span._attributes.get(ATTR_TURN_AGENT_TEXT)
        assert exported == long_response.strip()
        assert len(exported) > 512


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

    def test_agent_turn_uses_worker_agent_name_when_no_label(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-worker-name")
        state = get_job_bootstrap().state
        state.worker_agent_name = "hotel-receptionist"
        state.open_agent_turn_index = 1

        span = _make_span("agent_turn", {ATTR_LK_RESPONSE_TEXT: "Hello"})
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "hotel-receptionist"

    def test_function_tool_prefers_label_over_dispatch_id_attr(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-ad-label")
        state = get_job_bootstrap().state
        state.agent_label = "greeter"

        span = _make_span("function_tool", {
            ATTR_LK_AGENT_NAME: "AD_GAJ5UrwGKqsZ",
            ATTR_LK_FNC_TOOL_NAME: "to_takeaway",
            ATTR_LK_FNC_TOOL_OUTPUT: "ok",
        })
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "greeter"

    def test_function_tool_ignores_dispatch_id_when_no_label(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-ad-only")
        state = get_job_bootstrap().state
        state.worker_agent_name = "AD_NrRASAvBPGAx"
        state.agent_label = ""

        import parlot.instrumentation.livekit._auto as _auto

        _auto._configured_agent_id = "agent-f1e2d3"

        span = _make_span("function_tool", {
            ATTR_LK_AGENT_NAME: "AD_NrRASAvBPGAx",
            ATTR_LK_FNC_TOOL_NAME: "to_reservation",
            ATTR_LK_FNC_TOOL_OUTPUT: "ok",
        })
        proc.on_end(span)
        # No topology identity from LiveKit — use configured agent_id, never AD_*.
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "agent-f1e2d3"

    def test_function_tool_uses_label_attr_for_unnamed_worker(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-unnamed-labeled")
        state = get_job_bootstrap().state
        state.worker_agent_name = ""
        state.agent_label = ""

        span = _make_span("function_tool", {
            ATTR_LK_AGENT_LABEL: "greeter",
            ATTR_LK_AGENT_NAME: "AD_fSkdjADywDrh",
            ATTR_LK_FNC_TOOL_NAME: "to_reservation",
            ATTR_LK_FNC_TOOL_OUTPUT: "ok",
        })
        proc.on_end(span)
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "greeter"


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
        assert span._attributes[ATTR_SESSION_AMD] == "voicemail"
        assert span._attributes[ATTR_TURN_INDEX] == 0

    def test_amd_on_root(self) -> None:
        proc = LiveKitGenAIProcessor()
        job_id = "job-amd-root"
        _bootstrap_proc(proc, job_id)
        proc.on_end(_make_span("amd", {ATTR_AMD_CATEGORY: "human"}))
        assert get_job_bootstrap().state.amd == "human"


class TestHandoffSpanEnrichment:
    def test_agent_handoff_transfer_and_conversation_id(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        span = _make_span(SPAN_AGENT_HANDOFF, {
            ATTR_AGENT_TRANSFER_FROM: "agent-old",
            ATTR_AGENT_TRANSFER_TO: "agent-new",
        })
        proc.on_end(span)
        assert span._attributes[ATTR_AGENT_TRANSFER_FROM] == "agent-old"
        assert span._attributes[ATTR_AGENT_TRANSFER_TO] == "agent-new"
        assert span._attributes[ATTR_GEN_AI_AGENT_NAME] == "agent-new"
        assert ATTR_GEN_AI_CONVERSATION_ID in span._attributes
        assert ATTR_SESSION_ID in span._attributes

    def test_handoff_updates_agent_label_for_subsequent_turns(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.agent_label = "hotel-receptionist"
        span = _make_span(SPAN_AGENT_HANDOFF, {
            ATTR_AGENT_TRANSFER_FROM: "hotel-receptionist",
            ATTR_AGENT_TRANSFER_TO: "get_email_task",
        })
        proc.on_end(span)
        assert state.agent_label == "get_email_task"


class TestPipelineTurnIndex:
    """Regression: later TTS/LLM must not collapse onto turn 1 after greeting."""

    def test_greeting_pipeline_uses_turn_1_when_nothing_open(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        assert state.turn_count == 0
        assert state.open_agent_turn_index is None

        tts = _make_span("tts_node")
        proc.on_end(tts)
        assert tts._attributes[ATTR_TURN_INDEX] == 1

        llm = _make_span("llm_node")
        proc.on_end(llm)
        assert llm._attributes[ATTR_TURN_INDEX] == 1

    def test_pipeline_uses_open_agent_turn_not_completed_turn_count(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        # Greeting already committed; next user opened agent turn 3.
        state.turn_count = 2
        state.open_agent_turn_index = 3

        tts = _make_span("tts_node")
        proc.on_end(tts)
        assert tts._attributes[ATTR_TURN_INDEX] == 3

    def test_pipeline_after_open_cleared_uses_next_turn_not_stale_count(self) -> None:
        """Consecutive agent reply (handoff on_enter) with open cleared."""
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.turn_count = 3
        state.open_agent_turn_index = None

        tts = _make_span("tts_node")
        proc.on_end(tts)
        # Must not reuse completed turn 3 (the bug that piled spans onto turn 1
        # when turn_count stayed at 1 after the greeting).
        assert tts._attributes[ATTR_TURN_INDEX] == 4

    def test_on_start_keeps_index_after_agent_commit_clears_open(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.turn_count = 2
        state.open_agent_turn_index = 3

        tts = _make_span("tts_node")
        proc.on_start(tts)
        assert tts._attributes[ATTR_TURN_INDEX] == 3

        # conversation_item_added commits the agent turn and clears open.
        state.turn_count = 3
        state.open_agent_turn_index = None

        proc.on_end(tts)
        assert tts._attributes[ATTR_TURN_INDEX] == 3

    def test_active_turn_index_matches_commit_agent_message(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc)
        state = get_job_bootstrap().state
        state.turn_count = 1
        state.open_agent_turn_index = None
        assert proc._turns.active_turn_index(state, "tts_node") == 2
        assert proc._turns.active_turn_index(state, "llm_request_run") == 2


def test_processor_on_end_failure_logs_descriptively_without_traceback(caplog) -> None:
    proc = LiveKitGenAIProcessor()
    span = _make_span("some_span", {})
    with patch.object(proc, "_enrich", side_effect=RuntimeError("enrichment failed")):
        with caplog.at_level("DEBUG"):
            proc.on_end(span)

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    assert "parlot: LiveKitGenAIProcessor failed on span 'some_span' — enrichment failed" in error_records[0].message
    assert error_records[0].exc_info is None

