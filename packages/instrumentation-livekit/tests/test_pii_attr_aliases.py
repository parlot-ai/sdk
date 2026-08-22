"""Tests for Agents 1.7 ``lk.pii.*`` attribute keys and legacy ``lk.*`` aliases."""

from __future__ import annotations

import json

from parlot.core.attrs import (
    ATTR_AGENT_INSTRUCTIONS_EXCERPT,
    ATTR_PARTICIPANT_CHANNEL_IDENTITY,
    ATTR_SESSION_USER_ID,
    ATTR_TOOL_INPUT_PAYLOAD,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_USER_TEXT,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_CHAT_CTX_LEGACY,
    ATTR_FUNCTION_TOOL_ARGS_LEGACY,
    ATTR_FUNCTION_TOOL_OUTPUT_LEGACY,
    ATTR_INSTRUCTIONS_LEGACY,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_FNC_TOOL_ARGS,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_INSTRUCTIONS,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_TTS_INPUT_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_LK_USER_TRANSCRIPT,
    ATTR_PARTICIPANT_IDENTITY,
    ATTR_PARTICIPANT_IDENTITY_LEGACY,
    ATTR_RESPONSE_TEXT_LEGACY,
    ATTR_ROOM_NAME_LEGACY,
    ATTR_TTS_INPUT_TEXT_LEGACY,
    ATTR_USER_INPUT_LEGACY,
    ATTR_USER_TRANSCRIPT_LEGACY,
    attr_get,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor

from test_livekit_processor import _bootstrap_proc, _make_span


class TestAttrGetHelper:
    def test_prefers_primary_when_present(self) -> None:
        attrs = {ATTR_LK_USER_INPUT: "new", ATTR_USER_INPUT_LEGACY: "old"}
        assert attr_get(attrs, ATTR_LK_USER_INPUT, ATTR_USER_INPUT_LEGACY) == "new"

    def test_falls_back_to_legacy(self) -> None:
        attrs = {ATTR_USER_INPUT_LEGACY: "old"}
        assert attr_get(attrs, ATTR_LK_USER_INPUT, ATTR_USER_INPUT_LEGACY) == "old"

    def test_returns_default_when_missing(self) -> None:
        assert attr_get({}, ATTR_LK_USER_INPUT, ATTR_USER_INPUT_LEGACY, default="") == ""


class TestPiiAndLegacySpanKeys:
    def test_agent_turn_accepts_pii_keys(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
        _bootstrap_proc(proc, "job-pii-new")
        span = _make_span(
            "agent_turn",
            {
                ATTR_LK_USER_INPUT: "hello pii",
                ATTR_LK_RESPONSE_TEXT: "hi from agent",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "hello pii"
        assert span._attributes.get(ATTR_TURN_AGENT_TEXT) == "hi from agent"
        event_names = [e.name for e in span._events]
        assert EVENT_GEN_AI_USER_MESSAGE in event_names
        assert EVENT_GEN_AI_ASSISTANT_MESSAGE in event_names

    def test_agent_turn_accepts_legacy_keys(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
        _bootstrap_proc(proc, "job-pii-legacy")
        span = _make_span(
            "agent_turn",
            {
                ATTR_USER_INPUT_LEGACY: "hello legacy",
                ATTR_RESPONSE_TEXT_LEGACY: "legacy reply",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "hello legacy"
        assert span._attributes.get(ATTR_TURN_AGENT_TEXT) == "legacy reply"
        event_names = [e.name for e in span._events]
        assert EVENT_GEN_AI_USER_MESSAGE in event_names
        assert EVENT_GEN_AI_ASSISTANT_MESSAGE in event_names

    def test_user_turn_accepts_legacy_transcript(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-pii-transcript")
        span = _make_span(
            "user_turn",
            {ATTR_USER_TRANSCRIPT_LEGACY: "spoken legacy"},
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "spoken legacy"

    def test_user_turn_accepts_pii_transcript(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-pii-transcript-new")
        span = _make_span(
            "user_turn",
            {ATTR_LK_USER_TRANSCRIPT: "spoken pii"},
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "spoken pii"

    def test_llm_node_accepts_legacy_chat_ctx_and_instructions(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-pii-chat")
        chat_ctx = json.dumps(
            {
                "items": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": "legacy chat ctx user",
                    }
                ]
            }
        )
        span = _make_span(
            "llm_node",
            {
                ATTR_CHAT_CTX_LEGACY: chat_ctx,
                ATTR_INSTRUCTIONS_LEGACY: "You are a legacy instructions agent.",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "legacy chat ctx user"
        assert "legacy instructions agent" in span._attributes.get(
            ATTR_AGENT_INSTRUCTIONS_EXCERPT, ""
        )

    def test_llm_node_accepts_pii_chat_ctx_and_instructions(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-pii-chat-new")
        chat_ctx = json.dumps(
            {
                "items": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": "pii chat ctx user",
                    }
                ]
            }
        )
        span = _make_span(
            "llm_node",
            {
                ATTR_LK_CHAT_CTX: chat_ctx,
                ATTR_LK_INSTRUCTIONS: "You are a pii instructions agent.",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TURN_USER_TEXT) == "pii chat ctx user"
        assert "pii instructions agent" in span._attributes.get(
            ATTR_AGENT_INSTRUCTIONS_EXCERPT, ""
        )

    def test_function_tool_accepts_legacy_args_and_output(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
        _bootstrap_proc(proc, "job-pii-tool")
        span = _make_span(
            "function_tool",
            {
                ATTR_LK_FNC_TOOL_NAME: "lookup",
                ATTR_FUNCTION_TOOL_ARGS_LEGACY: '{"q":"legacy"}',
                ATTR_FUNCTION_TOOL_OUTPUT_LEGACY: "legacy-out",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TOOL_INPUT_PAYLOAD) == '{"q":"legacy"}'

    def test_function_tool_accepts_pii_args_and_output(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
        _bootstrap_proc(proc, "job-pii-tool-new")
        span = _make_span(
            "function_tool",
            {
                ATTR_LK_FNC_TOOL_NAME: "lookup",
                ATTR_LK_FNC_TOOL_ARGS: '{"q":"pii"}',
                ATTR_LK_FNC_TOOL_OUTPUT: "pii-out",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_TOOL_INPUT_PAYLOAD) == '{"q":"pii"}'

    def test_tts_request_accepts_legacy_input_text(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
        _bootstrap_proc(proc, "job-pii-tts")
        span = _make_span(
            "tts_request_run",
            {ATTR_TTS_INPUT_TEXT_LEGACY: "say legacy"},
        )
        proc.on_end(span)
        event_names = [e.name for e in span._events]
        assert EVENT_GEN_AI_ASSISTANT_MESSAGE in event_names

    def test_tts_request_accepts_pii_input_text(self) -> None:
        proc = LiveKitGenAIProcessor(capture_genai_content=True)
        _bootstrap_proc(proc, "job-pii-tts-new")
        span = _make_span(
            "tts_request_run",
            {ATTR_LK_TTS_INPUT_TEXT: "say pii"},
        )
        proc.on_end(span)
        event_names = [e.name for e in span._events]
        assert EVENT_GEN_AI_ASSISTANT_MESSAGE in event_names

    def test_participant_identity_legacy_and_pii(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-pii-identity")
        legacy = _make_span(
            "user_turn",
            {
                ATTR_USER_TRANSCRIPT_LEGACY: "hi",
                ATTR_PARTICIPANT_IDENTITY_LEGACY: "caller-legacy",
            },
        )
        proc.on_end(legacy)
        assert legacy._attributes.get(ATTR_SESSION_USER_ID) == "caller-legacy"
        assert (
            legacy._attributes.get(ATTR_PARTICIPANT_CHANNEL_IDENTITY) == "caller-legacy"
        )

        proc2 = LiveKitGenAIProcessor()
        _bootstrap_proc(proc2, "job-pii-identity-new")
        modern = _make_span(
            "user_turn",
            {
                ATTR_LK_USER_TRANSCRIPT: "hi",
                ATTR_PARTICIPANT_IDENTITY: "caller-pii",
            },
        )
        proc2.on_end(modern)
        assert modern._attributes.get(ATTR_SESSION_USER_ID) == "caller-pii"
        assert modern._attributes.get(ATTR_PARTICIPANT_CHANNEL_IDENTITY) == "caller-pii"

    def test_room_name_legacy_updates_session_state(self) -> None:
        proc = LiveKitGenAIProcessor()
        _bootstrap_proc(proc, "job-pii-room")
        span = _make_span(
            "user_turn",
            {
                ATTR_USER_TRANSCRIPT_LEGACY: "hi",
                ATTR_ROOM_NAME_LEGACY: "room-legacy",
            },
        )
        proc.on_end(span)
        assert span._attributes.get(ATTR_LK_ROOM_NAME) == "room-legacy"
