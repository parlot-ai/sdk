"""Tests for LiveKit AgentSession event bridge (semantic/commit layer)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_STAGE,
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_SESSION_USER_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_INTERRUPTED,
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_LANGUAGE,
    ATTR_TURN_PARTICIPANT_LABEL,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_USER_TEXT,
    ATTR_VOICE_STT_CONFIDENCE,
    SPAN_AGENT_HANDOFF,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_DIAR_SOURCE_REALTIME_INTERRUPT,
    ATTR_DIAR_SOURCE_STT_EVENT,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_JOB_ID,
    ATTR_LK_USER_TRANSCRIPT,
    ATTR_PARTICIPANT_IDENTITY,
    ATTR_TRANSCRIPT_CONFIDENCE,
)
from parlot.instrumentation.livekit._events import (
    LiveKitEventBridge,
    _message_text,
    _normalize_close_reason,
    install_session_hooks,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from bootstrap_helpers import bootstrap_via_agent_state

def _make_span(name: str, attributes: dict | None = None) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.context.trace_id = 0xDEADBEEF
    span.context.span_id = 0xABCDEF01
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
    _session, bootstrap = bootstrap_via_agent_state(proc, job_id)
    bootstrap.state.parlot_session_id = "sess-1"
    bootstrap.state.conversation_id = "conv-1"


def _event_bridge(proc: LiveKitGenAIProcessor) -> LiveKitEventBridge:
    tracer = proc._tracer
    assert tracer is not None
    return LiveKitEventBridge(proc, tracer)


def _parlot_turns(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.name == "parlot.turn"]


class TestEventBridgeTurns:
    def test_conversation_items_emit_turns_not_spans(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = _event_bridge(proc)
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
        assert turns[0].attributes[ATTR_TURN_USER_TEXT] == "Hello there"
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert turns[1].attributes[ATTR_TURN_AGENT_TEXT] == "Hi, how can I help?"

        # Text modality: no synthetic stt/tts companions.
        assert not [
            s for s in exporter.get_finished_spans() if s.name == SPAN_VOICE_STT
        ]
        assert not [
            s for s in exporter.get_finished_spans() if s.name == SPAN_VOICE_TTS
        ]

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

    def test_agent_voice_companion_uses_tts_role(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = _event_bridge(proc)
        proc.set_turn_source("events")
        bridge._on_user_input_transcribed(
            SimpleNamespace(is_final=True, speaker_id="spk-1", language="en")
        )
        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-u-voice",
                    type="message",
                    role="user",
                    text_content="Hello",
                    interrupted=False,
                    metrics=None,
                )
            )
        )
        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-a-voice",
                    type="message",
                    role="assistant",
                    text_content="Welcome",
                    interrupted=False,
                    metrics=None,
                )
            )
        )
        agent_tts = [s for s in exporter.get_finished_spans() if s.name == SPAN_VOICE_TTS]
        assert len(agent_tts) == 1
        assert agent_tts[0].attributes[ATTR_TURN_AGENT_TEXT] == "Welcome"
        assert agent_tts[0].attributes[ATTR_AGENT_ROLE] == "tts"
        assert agent_tts[0].attributes[ATTR_AGENT_STAGE] == "turn"
        assert agent_tts[0].attributes[ATTR_TURN_INPUT_MODALITY] == "voice"

    def test_agent_text_modality_stamps_turn_without_companion(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        from parlot.instrumentation.livekit._session import get_job_bootstrap

        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        bootstrap.state.last_user_input_modality = "text"
        proc.set_turn_source("events")
        proc.commit_agent_message("Console reply")

        assert not [
            s for s in exporter.get_finished_spans() if s.name == SPAN_VOICE_TTS
        ]
        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_AGENT_TEXT] == "Console reply"
        assert turns[0].attributes[ATTR_TURN_INPUT_MODALITY] == "text"

    def test_user_transcription_meta_applied_to_turn(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = _event_bridge(proc)

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
        assert turn.attributes[ATTR_TURN_LANGUAGE] == "en"

    def test_session_usage_overrides_span_token_accumulation(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        bridge = _event_bridge(proc)

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
        bridge = _event_bridge(proc)

        bridge._on_function_tools_executed(
            SimpleNamespace(function_calls=[1, 2], function_call_outputs=[1, 2])
        )

        from parlot.instrumentation.livekit._session import get_job_bootstrap

        state = get_job_bootstrap().state
        assert state.tool_call_count == 2
        assert len(state.tool_execution_ns_queue) == 2

    def test_agent_handoff_deduped_and_recorded(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        bridge = _event_bridge(proc)

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

    def test_message_text_extracts_audio_content_transcript(self) -> None:
        audio = SimpleNamespace(transcript="voice transcript")
        item = SimpleNamespace(
            text_content=None,
            content=[audio],
        )
        assert _message_text(item) == "voice transcript"

    def test_events_mode_stamps_user_turn_from_committed_message(self) -> None:
        proc, _exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        bridge = _event_bridge(proc)

        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-u3",
                    type="message",
                    role="user",
                    text_content="Book tomorrow please",
                    interrupted=False,
                    metrics=None,
                )
            )
        )

        span = _make_span(
            "user_turn",
            {
                ATTR_LK_USER_TRANSCRIPT: "wrong fallback transcript",
                ATTR_LK_JOB_ID: "job-ev",
            },
        )
        proc.on_end(span)
        assert span._attributes[ATTR_TURN_USER_TEXT] == "Book tomorrow please"

    def test_events_mode_llm_node_does_not_stamp_turn_user_text(self) -> None:
        proc, _exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        span = _make_span(
            "llm_node",
            {ATTR_LK_CHAT_CTX: '{"items":[{"type":"message","role":"user","content":"polluted"}]}'},
        )
        proc.on_end(span)
        assert ATTR_TURN_USER_TEXT not in span._attributes

    def test_events_mode_user_turn_before_commit_still_gets_text(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        bridge = _event_bridge(proc)

        early_span = _make_span(
            "user_turn",
            {ATTR_LK_USER_TRANSCRIPT: "early transcript", ATTR_LK_JOB_ID: "job-ev"},
        )
        proc.on_end(early_span)
        assert ATTR_TURN_USER_TEXT not in early_span._attributes

        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-u4",
                    type="message",
                    role="user",
                    text_content="Committed after pipeline span",
                    interrupted=False,
                    metrics=None,
                )
            )
        )

        user_spans = [
            s
            for s in exporter.get_finished_spans()
            if s.name == "stt"
            and s.attributes.get(ATTR_TURN_USER_TEXT) == "Committed after pipeline span"
        ]
        # Text modality: utterance lives on parlot.turn, not a synthetic stt companion.
        assert user_spans == []
        turns = _parlot_turns(exporter)
        assert len(turns) == 1
        assert turns[0].attributes[ATTR_TURN_USER_TEXT] == "Committed after pipeline span"
        assert turns[0].attributes[ATTR_TURN_INDEX] == 1

    def test_agent_greets_first_user_utterance_at_user_turn_index(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        bridge = _event_bridge(proc)

        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-a0",
                    type="message",
                    role="assistant",
                    text_content="Hello!",
                    interrupted=False,
                    metrics=None,
                )
            )
        )
        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-u5",
                    type="message",
                    role="user",
                    text_content="I need help",
                    interrupted=False,
                    metrics=None,
                )
            )
        )

        turns = _parlot_turns(exporter)
        assert len(turns) == 2
        assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
        assert turns[0].attributes[ATTR_TURN_INDEX] == 1
        assert turns[0].attributes[ATTR_TURN_AGENT_TEXT] == "Hello!"
        assert turns[1].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "user"
        assert turns[1].attributes[ATTR_TURN_INDEX] == 2
        assert turns[1].attributes[ATTR_TURN_USER_TEXT] == "I need help"

        # Agent greet uses default voice modality → tts companion; user is text → no stt.
        assert any(
            s.name == SPAN_VOICE_TTS
            and s.attributes.get(ATTR_TURN_AGENT_TEXT) == "Hello!"
            for s in exporter.get_finished_spans()
        )
        assert not any(
            s.name == SPAN_VOICE_STT
            and s.attributes.get(ATTR_TURN_USER_TEXT) == "I need help"
            for s in exporter.get_finished_spans()
        )

        late_pipeline = _make_span(
            "user_turn",
            {ATTR_LK_USER_TRANSCRIPT: "stale", ATTR_LK_JOB_ID: "job-ev"},
        )
        proc.on_end(late_pipeline)
        assert late_pipeline._attributes.get(ATTR_TURN_USER_TEXT) == "I need help"
        assert late_pipeline._attributes.get(ATTR_TURN_INDEX) == 2

    def test_user_turn_captures_participant_identity_on_session(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")

        span = _make_span(
            "user_turn",
            {
                ATTR_PARTICIPANT_IDENTITY: "caller-123",
                ATTR_LK_JOB_ID: "job-ev",
            },
        )
        proc.on_end(span)

        from parlot.instrumentation.livekit._session import get_job_bootstrap

        bootstrap = get_job_bootstrap()
        assert bootstrap.state.user_id == "caller-123"
        assert bootstrap.session_span._attributes.get(ATTR_SESSION_USER_ID) == "caller-123"

    def test_realtime_interrupt_user_turn_uses_agent_media_boundary(self) -> None:
        proc, exporter = _proc_with_exporter()
        _bootstrap(proc)
        proc.set_turn_source("events")
        from parlot.instrumentation.livekit._session import get_job_bootstrap

        bootstrap = get_job_bootstrap()
        anchor_wall_ms = 1_000_000_000
        proc.set_recording_anchor_wall_ms(bootstrap.state, anchor_wall_ms)
        bootstrap.state.open_agent_turn_index = 3
        bootstrap.state.turn_count = 2
        bootstrap.state.agent_label = "story_agent"

        agent_started = anchor_wall_ms / 1000.0 + 43.044
        agent_stopped = anchor_wall_ms / 1000.0 + 52.232
        bridge = _event_bridge(proc)

        bridge._on_conversation_item_added(
            SimpleNamespace(
                item=SimpleNamespace(
                    id="msg-a-int",
                    type="message",
                    role="assistant",
                    text_content="Hola, como estas?",
                    interrupted=True,
                    metrics={
                        "started_speaking_at": agent_started,
                        "stopped_speaking_at": agent_stopped,
                    },
                )
            )
        )

        user_commit_wall = anchor_wall_ms / 1000.0 + 55.0
        with patch(
            "parlot.instrumentation.livekit._turn_enricher.time.time",
            return_value=user_commit_wall,
        ):
            bridge._on_conversation_item_added(
                SimpleNamespace(
                    item=SimpleNamespace(
                        id="msg-u-int",
                        type="message",
                        role="user",
                        text_content="Wait wait wait",
                        interrupted=False,
                        metrics=None,
                    )
                )
            )

        turns = _parlot_turns(exporter)
        agent_turns = [
            t
            for t in turns
            if t.attributes.get(ATTR_TURN_PARTICIPANT_ROLE) == "agent"
        ]
        user_turns = [
            t
            for t in turns
            if t.attributes.get(ATTR_TURN_PARTICIPANT_ROLE) == "user"
        ]
        assert len(agent_turns) == 1
        assert len(user_turns) == 1
        assert agent_turns[0].attributes[ATTR_TURN_INTERRUPTED] is True
        assert agent_turns[0].attributes[ATTR_TURN_MEDIA_END_MS] == 52_232
        assert user_turns[0].attributes[ATTR_TURN_MEDIA_START_MS] == 52_232
        assert user_turns[0].attributes[ATTR_TURN_INPUT_MODALITY] == "voice"
        assert (
            user_turns[0].attributes[ATTR_PARTICIPANT_DIAR_SOURCE]
            == ATTR_DIAR_SOURCE_REALTIME_INTERRUPT
        )
        assert user_turns[0].attributes[ATTR_TURN_PARTICIPANT_LABEL] == "Caller"


class TestNormalizeCloseReason:
    def test_enum_like_reason_string(self) -> None:
        assert _normalize_close_reason("CloseReason.PARTICIPANT_DISCONNECTED") == (
            "participant_disconnected"
        )

    def test_lowercase_enum_value(self) -> None:
        assert _normalize_close_reason("participant_disconnected") == (
            "participant_disconnected"
        )


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
        assert "agent_state_changed" in handlers
        assert "metrics_collected" not in handlers
