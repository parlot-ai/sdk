"""Agents 1.8 GenAI message attrs, realtime spans, and provider IDs."""

from __future__ import annotations

import json

from parlot.core.attrs import (
    ATTR_GEN_AI_INPUT_MESSAGES,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUTPUT_MESSAGES,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_REASONING_OUTPUT_TOKENS,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_SYSTEM_INSTRUCTIONS,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_USER_TEXT,
    GEN_AI_OP_GENERATE_CONTENT,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
)
from parlot.instrumentation.livekit._genai_messages import (
    parse_genai_messages,
    preview_from_genai_messages,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._span_rename import (
    apply_livekit_span_rename,
    remap_livekit_span_name,
)
from parlot.instrumentation.livekit._span_util import (
    normalize_provider_name,
    provider_to_system,
)

from test_livekit_processor import _bootstrap_proc, _make_span


def test_parse_genai_messages_parts_format() -> None:
    raw = json.dumps(
        [
            {
                "role": "user",
                "parts": [{"type": "text", "content": "Weather in Paris?"}],
            },
            {
                "role": "assistant",
                "parts": [{"type": "text", "content": "Rainy"}],
            },
        ]
    )
    msgs = parse_genai_messages(raw)
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Weather in Paris?"
    user, assistant = preview_from_genai_messages(
        {
            ATTR_GEN_AI_INPUT_MESSAGES: raw,
            ATTR_GEN_AI_OUTPUT_MESSAGES: json.dumps(
                [{"role": "assistant", "parts": [{"content": "Rainy"}]}]
            ),
        }
    )
    assert user == "Weather in Paris?"
    assert assistant == "Rainy"


def test_normalize_provider_names() -> None:
    assert normalize_provider_name("api.openai.com") == "openai"
    assert normalize_provider_name("AWS Bedrock") == "aws.bedrock"
    assert normalize_provider_name("aws.bedrock") == "aws.bedrock"
    assert normalize_provider_name("google") == "gcp.gen_ai"
    assert normalize_provider_name("gcp.gen_ai") == "gcp.gen_ai"
    assert provider_to_system("google") == "gcp.gen_ai"
    assert provider_to_system("aws.bedrock") == "aws.bedrock"


class _RenameSpan:
    """Mirrors OTel ReadableSpan ``_name`` mutation used by apply_livekit_span_rename."""

    def __init__(self, name: str, attributes: dict | None = None) -> None:
        self._name = name
        self._attributes = dict(attributes or {})

    @property
    def name(self) -> str:
        return self._name

    @property
    def attributes(self) -> dict:
        return self._attributes


def test_realtime_inference_rename_preserves_generate_content() -> None:
    assert (
        remap_livekit_span_name(
            "realtime_inference", {"gen_ai.request.model": "gpt-4o-realtime"}
        )
        == "chat gpt-4o-realtime"
    )
    assert remap_livekit_span_name("realtime_metrics", {}) is None

    span = _RenameSpan(
        "realtime_inference",
        {
            "gen_ai.request.model": "gpt-4o-realtime",
            ATTR_GEN_AI_OP_NAME: GEN_AI_OP_GENERATE_CONTENT,
        },
    )
    apply_livekit_span_rename(span)  # type: ignore[arg-type]
    assert span.name == "chat gpt-4o-realtime"
    assert span._attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_GENERATE_CONTENT


def test_realtime_inference_sets_generate_content_when_missing() -> None:
    span = _RenameSpan(
        "realtime_inference",
        {"gen_ai.request.model": "gpt-4o-realtime"},
    )
    apply_livekit_span_rename(span)  # type: ignore[arg-type]
    assert span._attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_GENERATE_CONTENT


def test_llm_node_prefers_genai_messages_no_legacy_events() -> None:
    proc = LiveKitGenAIProcessor(capture_genai_content=True)
    _bootstrap_proc(proc, "job-genai-18")
    messages = json.dumps(
        [
            {"role": "user", "parts": [{"content": "hello 18"}]},
            {"role": "assistant", "parts": [{"content": "hi 18"}]},
        ]
    )
    span = _make_span(
        "llm_node",
        {
            ATTR_GEN_AI_INPUT_MESSAGES: messages,
            ATTR_GEN_AI_OUTPUT_MESSAGES: json.dumps(
                [{"role": "assistant", "parts": [{"content": "hi 18"}]}]
            ),
            ATTR_GEN_AI_SYSTEM_INSTRUCTIONS: "Be helpful",
            ATTR_GEN_AI_PROVIDER: "api.openai.com",
            "gen_ai.request.model": "gpt-4o",
        },
    )
    # Spans mode so turn text is stamped from LLM content.
    proc.set_turn_source("spans")
    proc.on_end(span)
    assert span._attributes.get(ATTR_TURN_USER_TEXT) == "hello 18"
    assert span._attributes.get(ATTR_TURN_AGENT_TEXT) == "hi 18"
    assert span._attributes.get(ATTR_GEN_AI_PROVIDER) == "openai"
    assert span._attributes.get(ATTR_GEN_AI_SYSTEM) == "openai"
    assert ATTR_GEN_AI_INPUT_MESSAGES in (span._attributes or {})
    event_names = [e.name for e in span._events]
    assert EVENT_GEN_AI_USER_MESSAGE not in event_names
    assert EVENT_GEN_AI_ASSISTANT_MESSAGE not in event_names


def test_capture_off_strips_genai_content_attrs() -> None:
    proc = LiveKitGenAIProcessor(capture_genai_content=False)
    _bootstrap_proc(proc, "job-genai-strip")
    span = _make_span(
        "llm_node",
        {
            ATTR_GEN_AI_INPUT_MESSAGES: json.dumps(
                [{"role": "user", "content": "secret"}]
            ),
            "gen_ai.request.model": "gpt-4o",
        },
    )
    proc.set_turn_source("spans")
    proc.on_end(span)
    assert ATTR_GEN_AI_INPUT_MESSAGES not in (span._attributes or {})
    assert span._attributes.get(ATTR_TURN_USER_TEXT) is None


def test_realtime_inference_enrichment() -> None:
    proc = LiveKitGenAIProcessor(capture_genai_content=True)
    _bootstrap_proc(proc, "job-realtime")
    span = _make_span(
        "realtime_inference",
        {
            ATTR_GEN_AI_INPUT_MESSAGES: json.dumps(
                [{"role": "user", "content": "hi realtime"}]
            ),
            ATTR_GEN_AI_OUTPUT_MESSAGES: json.dumps(
                [{"role": "assistant", "content": "hello"}]
            ),
            ATTR_GEN_AI_PROVIDER: "openai",
            "gen_ai.request.model": "gpt-4o-realtime",
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 5,
            ATTR_GEN_AI_REASONING_OUTPUT_TOKENS: 3,
        },
    )
    proc.set_turn_source("spans")
    proc.on_end(span)
    assert span._attributes.get(ATTR_GEN_AI_OP_NAME) == GEN_AI_OP_GENERATE_CONTENT
    assert span._attributes.get(ATTR_TURN_USER_TEXT) == "hi realtime"
    assert span._attributes.get(ATTR_TURN_AGENT_TEXT) == "hello"
