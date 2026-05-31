"""Tests for LiveKit AgentSession event bridge (semantic/commit layer)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_SESSION_TOTAL_INPUT_TOKENS,
    ATTR_SESSION_TOTAL_OUTPUT_TOKENS,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_VOICE_STT_CONFIDENCE,
    SPAN_AGENT_HANDOFF,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_DIAR_SOURCE_STT_EVENT,
    ATTR_LK_JOB_ID,
    ATTR_LK_USER_TRANSCRIPT,
    ATTR_TRANSCRIPT_CONFIDENCE,
)
from parlot.instrumentation.livekit._events import LiveKitEventBridge, install_session_hooks
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor

def _make_span(name: str, attributes: dict | None = None) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.context.trace_id = 0xDEADBEEF
    span.attributes = span._attributes
    return span


def _proc_with_exporter() -> tuple[LiveKitGenAIProcessor, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    proc = LiveKitGenAIProcessor()
    provider.add_span_processor(proc)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    proc.set_tracer(provider.get_tracer("test"))
    return proc, exporter


def _bootstrap(proc: LiveKitGenAIProcessor, job_id: str = "job-ev") -> None:
    entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: job_id})
    proc.on_start(entry)
    from parlot.instrumentation.livekit._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    assert bootstrap is not None
    bootstrap.state.parlot_session_id = "sess-1"
    bootstrap.state.conversation_id = "conv-1"


def _parlot_turns(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.name == "parlot.turn"]


class TestEventBridgeTurns:
    def test_conversation_items_emit_turns_not_spans(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = LiveKitEventBridge(proc, proc._tracer)
        bridge.install(SimpleNamespace(on=lambda *_a, **_k: (lambda fn: fn)))

        user_item = SimpleNamespace(
            id="msg-u1",
            type="message",
            role="user",
            text_content="Hello there",
            interrupted=False,
            metrics=None,
        )
        bridge._on_conversation_item_added(SimpleNamespace(item=user_item))

        agent_item = SimpleNamespace(
            id="msg-a1",
            type="message",
            role="assistant",
            text_content="Hi, how can I help?",
            interrupted=False,
            metrics=SimpleNamespace(e2e_latency=1.2, llm_ttft=0.3),
        )
        bridge._on_conversation_item_added(SimpleNamespace(item=agent_item))

        turns = _parlot_turns(exporter)
        assert len(turns) == 2
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"

        proc.on_end(
            _make_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "Hello there"},
            )
        )
        proc.on_end(
            _make_span(
                "agent_turn",
                {ATTR_LK_USER_TRANSCRIPT: "Hello there"},
            )
        )
        assert len(_parlot_turns(exporter)) == 2

    def test_user_transcription_meta_applied_to_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = LiveKitEventBridge(proc, proc._tracer)

        bridge._on_user_input_transcribed(
            SimpleNamespace(is_final=True, speaker_id="spk-2", language="en")
        )
        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-u2",
                    type="message",
                    role="user",
                    text_content="Hey",
                    interrupted=False,
                    metrics=None,
                )
            )
        )

        turn = _parlot_turns(exporter)[0]
        assert turn.attributes[ATTR_TURN_PARTICIPANT_ID] == "spk-2"
        assert turn.attributes[ATTR_PARTICIPANT_DIAR_SOURCE] == ATTR_DIAR_SOURCE_STT_EVENT
        assert turn.attributes[ATTR_TURN_INPUT_MODALITY] == "voice"

    def test_session_usage_overrides_span_token_accumulation(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = LiveKitEventBridge(proc, proc._tracer)

        usage = SimpleNamespace(
            model_usage=[
                SimpleNamespace(input_tokens=100, output_tokens=40),
                SimpleNamespace(input_tokens=50, output_tokens=10),
            ]
        )
        bridge._on_session_usage_updated(SimpleNamespace(usage=usage))

        proc.on_end(
            _make_span(
                "llm_request",
                {"gen_ai.usage.input_tokens": 999, "gen_ai.usage.output_tokens": 999},
            )
        )

        from parlot.instrumentation.livekit._session import get_job_bootstrap

        state = get_job_bootstrap().state
        assert state.total_input_tokens == 150
        assert state.total_output_tokens == 50

    def test_function_tools_executed_increments_count(self) -> None:
        proc, _exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = LiveKitEventBridge(proc, proc._tracer)

        bridge._on_function_tools_executed(
            SimpleNamespace(function_calls=[1, 2], function_call_outputs=[1, 2])
        )

        from parlot.instrumentation.livekit._session import get_job_bootstrap

        assert get_job_bootstrap().state.tool_call_count == 2

    def test_agent_handoff_deduped_and_recorded(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        bridge = LiveKitEventBridge(proc, proc._tracer)

        item = SimpleNamespace(
            id="ho-1",
            type="agent_handoff",
            old_agent_id="agent-a",
            new_agent_id="agent-b",
            created_at=1.0,
        )
        bridge._on_conversation_item_added(SimpleNamespace(item=item))
        bridge._on_conversation_item_added(SimpleNamespace(item=item))

        handoffs = [s for s in exporter.get_finished_spans() if s.name == SPAN_AGENT_HANDOFF]
        assert len(handoffs) == 1
        assert handoffs[0].attributes[ATTR_AGENT_TRANSFER_FROM] == "agent-a"
        assert handoffs[0].attributes[ATTR_AGENT_TRANSFER_TO] == "agent-b"

        from parlot.instrumentation.livekit._session import get_job_bootstrap

        state = get_job_bootstrap().state
        assert state.handoff_count == 1
        assert state.agent_chain == ["agent-b"]

    def test_user_turn_span_still_maps_confidence_in_events_mode(self) -> None:
        proc, _exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")

        span = _make_span(
            "user_turn",
            {ATTR_LK_USER_TRANSCRIPT: "hi", ATTR_TRANSCRIPT_CONFIDENCE: 0.91},
        )
        proc.on_end(span)
        assert span._attributes[ATTR_VOICE_STT_CONFIDENCE] == 0.91


class TestInstallSessionHooks:
    def test_install_sets_events_turn_source(self) -> None:
        proc, _exporter = _proc_with_exporter()
        _bootstrap(proc)

        handlers: dict[str, list] = {}

        def _on(event_name):
            def decorator(fn):
                handlers.setdefault(event_name, []).append(fn)
                return fn

            return decorator

        session = SimpleNamespace(on=_on)
        install_session_hooks(session, proc, proc._tracer)
        assert proc.turn_source == "events"
        assert "conversation_item_added" in handlers
        assert "close" in handlers
