"""Per-conversation session bootstrap: ``parlot.session`` + ContextVar scope."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from opentelemetry.trace import Span, Tracer

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_CONVERSATION_CHANNEL,
    ATTR_GEN_AI_AGENT_ID,
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID,
    ATTR_SESSION_AGENT_ID,
    ATTR_SESSION_MODALITY,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_SPEECH_WALL_END_MS,
    ATTR_TURN_SPEECH_WALL_START_MS,
)
from parlot.core.recording_timeline import media_segments_from_speech
from parlot.core.sdk_version import stamp_session_sdk_version
from parlot.core.session import (
    SessionState,
    get_active_session,
)
from parlot.core.session_lifecycle import (
    emit_parlot_session_close,
    force_flush_tracer_provider,
    start_parlot_session_span,
)
from parlot.core.session_registry import ConversationSessionRegistry
from parlot.core.turn_emit import emit_parlot_turn_root

from ._platform_refs import stamp_pipecat_platform_refs
from .attrs import PIPECAT_FRAMEWORK

logger = logging.getLogger("parlot.instrumentation.pipecat")


@dataclass
class _PipecatSessionState(SessionState):
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    open_turn_index: int | None = None
    # Parlot contract uses alternating user/agent turn indices (LiveKit-style).
    # Pipecat's native turn.number is one exchange; we allocate separate indices.
    open_user_turn_index: int | None = None
    open_agent_turn_index: int | None = None
    # True once the open user index has been reminted (STT-final path).
    user_turn_emitted: bool = False
    transport: str = ""
    close_emitted: bool = False


def allocate_user_turn_index(state: _PipecatSessionState) -> int:
    """Next Parlot turn index for user/STT (stable for the open Pipecat exchange)."""
    if state.open_user_turn_index is not None:
        return state.open_user_turn_index
    state.turn_count += 1
    state.open_user_turn_index = state.turn_count
    state.open_turn_index = state.open_user_turn_index
    return state.open_user_turn_index


def allocate_agent_turn_index(state: _PipecatSessionState) -> int:
    """Next Parlot turn index for agent/LLM/TTS (after any open user turn)."""
    if state.open_agent_turn_index is not None:
        return state.open_agent_turn_index
    if state.open_user_turn_index is not None:
        state.open_agent_turn_index = state.open_user_turn_index + 1
        state.turn_count = max(state.turn_count, state.open_agent_turn_index)
    else:
        state.turn_count += 1
        state.open_agent_turn_index = state.turn_count
    state.open_turn_index = state.open_agent_turn_index
    return state.open_agent_turn_index


def clear_open_turn_indices(state: _PipecatSessionState) -> None:
    state.open_user_turn_index = None
    state.open_agent_turn_index = None
    state.open_turn_index = None
    state.user_turn_emitted = False


_registry: ConversationSessionRegistry[_PipecatSessionState] = (
    ConversationSessionRegistry()
)
# Backward-compat alias for tests that clear the session map directly.
_sessions_by_conversation = _registry._sessions
_configured_agent_id: str = ""
_configured_agent_version: str = ""
_tracer: Tracer | None = None


def set_identity(agent_id: str, version: str) -> None:
    global _configured_agent_id, _configured_agent_version
    _configured_agent_id = agent_id
    _configured_agent_version = version


def configured_agent_id() -> str:
    """Live agent id (do not import ``_configured_agent_id`` by value)."""
    return _configured_agent_id


def configured_agent_version() -> str:
    return _configured_agent_version


def set_tracer(tracer: Tracer) -> None:
    global _tracer
    _tracer = tracer


def get_tracer() -> Tracer | None:
    return _tracer


def _stamp_session_identity(
    span: Span,
    *,
    conversation_id: str,
    state: _PipecatSessionState | None = None,
) -> None:
    span.set_attribute(ATTR_AGENT_FRAMEWORK, PIPECAT_FRAMEWORK)
    span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK, PIPECAT_FRAMEWORK)
    span.set_attribute(ATTR_CONVERSATION_CHANNEL, "voice")
    span.set_attribute(ATTR_SESSION_MODALITY, "voice")
    if _configured_agent_id:
        span.set_attribute(ATTR_GEN_AI_AGENT_ID, _configured_agent_id)
        span.set_attribute(ATTR_SESSION_AGENT_ID, _configured_agent_id)
        span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID, conversation_id)
    if _configured_agent_version:
        span.set_attribute(ATTR_GEN_AI_AGENT_VERSION, _configured_agent_version)
    stamp_session_sdk_version(span, state)
    stamp_pipecat_platform_refs(
        span,
        conversation_id=conversation_id,
        transport=(state.transport if state else ""),
    )


def ensure_session(
    conversation_id: str,
    *,
    transport: str = "",
) -> _PipecatSessionState | None:
    """Open or return a session for ``conversation_id``."""
    if not conversation_id:
        return None

    def _factory() -> tuple[Span, _PipecatSessionState] | None:
        if _tracer is None:
            logger.debug("No tracer; skipping pipecat session bootstrap")
            return None
        state = _PipecatSessionState(
            session_id="",  # filled after span start
            conversation_id=conversation_id,
            framework=PIPECAT_FRAMEWORK,
            transport=transport or "",
        )

        def _stamp(span: Span) -> None:
            _stamp_session_identity(
                span, conversation_id=conversation_id, state=state
            )

        span, session_id = start_parlot_session_span(
            _tracer,
            conversation_id=conversation_id,
            stamp_fn=_stamp,
        )
        state.session_id = session_id
        return span, state

    state = _registry.ensure(conversation_id, _factory)
    if state is not None:
        _registry.ensure_atexit(flush_all_sessions)
    return state


def emit_turn(
    state: _PipecatSessionState,
    *,
    turn_index: int,
    role: str = "agent",
    interrupted: bool = False,
    e2e_latency_s: float | None = None,
    llm_ttft_s: float | None = None,
    tts_ttfb_s: float | None = None,
    utterance_text: str = "",
    user_text: str = "",
    agent_text: str = "",
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> str:
    """Mint a contract ``parlot.turn`` on a fresh OTel trace. Returns trace_id hex."""
    if _tracer is None:
        return ""
    state.turn_count = max(state.turn_count, turn_index)
    state.open_turn_index = turn_index

    extra = {
        ATTR_TURN_PARTICIPANT_ID: role,
        ATTR_TURN_INPUT_MODALITY: "voice",
        ATTR_AGENT_FRAMEWORK: PIPECAT_FRAMEWORK,
    }
    if start_time_ns is not None and end_time_ns is not None:
        speech_start = int(start_time_ns) // 1_000_000
        speech_end = int(end_time_ns) // 1_000_000
        if speech_end >= speech_start:
            extra[ATTR_TURN_SPEECH_WALL_START_MS] = speech_start
            extra[ATTR_TURN_SPEECH_WALL_END_MS] = speech_end
            if getattr(state, "recording_anchor_wall_ms", None) is not None:
                media_start, media_end = media_segments_from_speech(
                    state, speech_start, speech_end
                )
                extra[ATTR_TURN_MEDIA_START_MS] = media_start
                extra[ATTR_TURN_MEDIA_END_MS] = media_end
    tid, _span_id = emit_parlot_turn_root(
        _tracer,
        session_id=state.session_id,
        conversation_id=state.conversation_id,
        turn_index=turn_index,
        participant_role=role,
        utterance_text=utterance_text,
        user_text=user_text,
        agent_text=agent_text,
        prev_trace_id=state.last_turn_trace_id,
        start_time_unix_ns=start_time_ns,
        end_time_unix_ns=end_time_ns,
        interrupted=interrupted,
        e2e_latency_s=e2e_latency_s,
        llm_ttft_s=llm_ttft_s,
        tts_ttfb_s=tts_ttfb_s,
        stamp_genai_conversation_id=True,
        extra_attrs=extra,
        stamp_fn=lambda span: stamp_pipecat_platform_refs(
            span, conversation_id=state.conversation_id
        ),
    )
    state.last_turn_trace_id = tid
    try:
        from ._metrics import get_metrics_recorder

        recorder = get_metrics_recorder()
        if recorder is not None and state.session_id:
            recorder.record_turn(
                session_id=state.session_id,
                turn_index=turn_index,
                participant_role=role,
                e2e_latency_s=e2e_latency_s,
                llm_ttft_s=llm_ttft_s,
                tts_ttfb_s=tts_ttfb_s,
                interrupted=interrupted,
            )
    except Exception:
        logger.debug("turn metrics record failed", exc_info=True)
    return tid


def close_session(conversation_id: str, *, reason: str = "completed") -> None:
    """End the session and emit ``parlot.session.close``."""
    if _tracer is None:
        _registry.pop(conversation_id)
        return

    def _closer(session_span: Span, state: _PipecatSessionState) -> None:
        if state.close_emitted:
            return
        state.close_emitted = True
        emit_parlot_session_close(
            _tracer,
            session_id=state.session_id,
            conversation_id=state.conversation_id,
            reason=reason,
            framework=PIPECAT_FRAMEWORK,
            stamp_fn=lambda span: _stamp_session_identity(
                span, conversation_id=conversation_id, state=state
            ),
            state=state,
        )
        _registry.end_and_clear(session_span, state)
        try:
            from ._metrics import get_metrics_recorder, shutdown_metrics

            recorder = get_metrics_recorder()
            if recorder is not None and state.session_id:
                recorder.record_session_close(
                    session_id=state.session_id,
                    turn_count=state.turn_count,
                    total_input_tokens=state.total_input_tokens,
                    total_output_tokens=state.total_output_tokens,
                )
            # Stops PeriodicExportingMetricReader so /v1/metrics goes quiet after
            # the WebRTC session ends (bot process stays up for the next call).
            shutdown_metrics()
        except Exception:
            logger.debug("metrics shutdown after close_session failed", exc_info=True)
        if not force_flush_tracer_provider(timeout_millis=10_000):
            logger.debug("force_flush after close_session failed")
        try:
            from ._auto import flush_session_logs

            flush_session_logs()
        except Exception:
            logger.debug("session log flush after close_session failed", exc_info=True)

    closed = _registry.close(conversation_id, closer=_closer, clear_active=False)
    if not closed:
        return


def flush_all_sessions() -> None:
    _registry.flush_all(
        lambda conversation_id: close_session(conversation_id, reason="process_exit")
    )


def lookup_session(conversation_id: str) -> _PipecatSessionState | None:
    return _registry.get_state(conversation_id)


def any_open_session() -> _PipecatSessionState | None:
    """Best-effort open session for log correlation (ContextVar may be empty).

    Pipecat's pipeline worker and the uvicorn/transport thread do not share
    ContextVars, so ``get_active_session()`` is often unset where loguru fires.
    """
    active = get_active_session()
    if isinstance(active, _PipecatSessionState) and active.session_id:
        return active
    return _registry.last_opened_state()
