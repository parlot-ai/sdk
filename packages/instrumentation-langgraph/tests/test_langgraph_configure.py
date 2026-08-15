"""Tests for langgraph configure() and callback spans."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_CONVERSATION_CHANNEL,
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_ID,
    ATTR_SESSION_MODALITY,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_USER_TEXT,
    SPAN_CONVERSATION_SESSION,
    SPAN_GEN_AI_INVOKE_AGENT,
    SPAN_PARLOT_TURN,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
    is_exportable_span_name,
)
from parlot.core.session import (
    SessionState,
    clear_active_session,
    session_owned,
    set_active_session,
)
from parlot.instrumentation.langgraph._callbacks import ParlotLangGraphCallbackHandler
from parlot.instrumentation.langgraph._session import (
    _sessions_by_thread,
    close_session,
    ensure_session,
    livekit_owns_session,
    set_channel_modality,
    set_tracer,
)


@pytest.fixture(autouse=True)
def _reset_session() -> None:
    clear_active_session()
    _sessions_by_thread.clear()
    set_channel_modality(channel="", modality="")
    yield
    clear_active_session()
    for tid in list(_sessions_by_thread):
        close_session(tid, reason="test_teardown")
    _sessions_by_thread.clear()
    set_channel_modality(channel="", modality="")


def test_export_allowlist_includes_genai() -> None:
    assert is_exportable_span_name("chat")
    assert is_exportable_span_name("execute_tool lookup")
    assert is_exportable_span_name(SPAN_GEN_AI_INVOKE_AGENT)
    assert is_exportable_span_name(SPAN_CONVERSATION_SESSION)


def test_callback_emits_invoke_agent_and_chat() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    set_tracer(tracer)

    handler = ParlotLangGraphCallbackHandler(tracer, capture_genai_content=True)
    run_id = uuid4()
    handler.on_chain_start(
        {"name": "my_graph"},
        {"messages": [{"type": "human", "content": "Hi there"}]},
        run_id=run_id,
        metadata={"thread_id": "t-1"},
        name="my_graph",
    )
    llm_id = uuid4()
    handler.on_llm_start(
        {"name": "ChatOpenAI"},
        ["hello"],
        run_id=llm_id,
        parent_run_id=run_id,
        metadata={"ls_model_name": "gpt-4o-mini", "ls_provider": "openai"},
    )
    handler.on_llm_end(
        type(
            "R",
            (),
            {
                "llm_output": {
                    "token_usage": {"prompt_tokens": 3, "completion_tokens": 5}
                },
                "generations": [],
            },
        )(),
        run_id=llm_id,
        parent_run_id=run_id,
    )
    tool_id = uuid4()
    handler.on_tool_start(
        {"name": "lookup"},
        "{}",
        run_id=tool_id,
        parent_run_id=run_id,
    )
    handler.on_tool_end("ok", run_id=tool_id, parent_run_id=run_id)
    handler.on_chain_end(
        {"messages": [{"type": "ai", "content": "Hello back"}]},
        run_id=run_id,
    )
    close_session("t-1", reason="completed")

    spans = list(exporter.get_finished_spans())
    names = [s.name for s in spans]
    assert SPAN_CONVERSATION_SESSION in names
    assert SPAN_PARLOT_TURN in names
    assert SPAN_GEN_AI_INVOKE_AGENT in names
    assert any(n.startswith("chat") for n in names)
    assert "execute_tool lookup" in names
    assert SPAN_VOICE_STT not in names
    assert SPAN_VOICE_TTS not in names

    session = next(s for s in spans if s.name == SPAN_CONVERSATION_SESSION)
    assert session.attributes.get(ATTR_SESSION_AGENT_FRAMEWORK) == "langgraph"
    assert session.attributes.get(ATTR_AGENT_FRAMEWORK) == "langgraph"
    # Channel/modality are not assumed — agent must configure them.
    assert ATTR_CONVERSATION_CHANNEL not in (session.attributes or {})
    assert ATTR_SESSION_MODALITY not in (session.attributes or {})

    turns = [s for s in spans if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 2
    user_turn = next(
        s for s in turns if s.attributes.get(ATTR_TURN_USER_TEXT) == "Hi there"
    )
    agent_turn = next(
        s for s in turns if s.attributes.get(ATTR_TURN_AGENT_TEXT) == "Hello back"
    )
    assert user_turn.attributes.get(ATTR_TURN_INDEX) == 1
    assert agent_turn.attributes.get(ATTR_TURN_INDEX) == 2
    assert ATTR_TURN_INPUT_MODALITY not in (user_turn.attributes or {})

    ops = [
        s
        for s in spans
        if s.name in (SPAN_GEN_AI_INVOKE_AGENT, "execute_tool lookup")
        or (s.name or "").startswith("chat")
    ]
    assert ops
    for span in ops:
        assert span.attributes.get(ATTR_SESSION_ID)
        assert span.attributes.get(ATTR_TURN_INDEX) == 2


def test_channel_webchat_stamps_text_modality() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_channel_modality(channel="webchat")

    handler = ParlotLangGraphCallbackHandler(tracer, capture_genai_content=True)
    run_id = uuid4()
    handler.on_chain_start(
        {"name": "g"},
        {"messages": [{"type": "human", "content": "hi"}]},
        run_id=run_id,
        metadata={"thread_id": "t-channel"},
        name="g",
    )
    handler.on_chain_end(
        {"messages": [{"type": "ai", "content": "yo"}]},
        run_id=run_id,
    )
    close_session("t-channel", reason="completed")

    spans = list(exporter.get_finished_spans())
    session = next(s for s in spans if s.name == SPAN_CONVERSATION_SESSION)
    assert session.attributes.get(ATTR_CONVERSATION_CHANNEL) == "webchat"
    assert session.attributes.get(ATTR_SESSION_MODALITY) == "text"
    turn = next(s for s in spans if s.name == SPAN_PARLOT_TURN)
    assert turn.attributes.get(ATTR_TURN_INPUT_MODALITY) == "text"


def test_livekit_owns_session_suppresses_contract() -> None:
    set_active_session(
        MagicMock(),
        SessionState(session_id="lk-1", framework="livekit"),
    )
    assert livekit_owns_session()
    assert session_owned(framework="livekit")
    assert ensure_session("t-2") is None
