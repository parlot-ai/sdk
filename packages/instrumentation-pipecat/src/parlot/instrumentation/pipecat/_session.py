"""Per-conversation session bootstrap: ``parlot.session`` + ContextVar scope."""

from __future__ import annotations

import atexit
import logging
import random
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, Status, StatusCode, Tracer, TraceFlags

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_CONVERSATION_CHANNEL,
    ATTR_GEN_AI_AGENT_ID,
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID,
    ATTR_SESSION_AGENT_ID,
    ATTR_SESSION_CLOSE_REASON,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_SESSION_MODALITY,
    ATTR_TURN_E2E_LATENCY_S,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_INTERRUPTED,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_PREV_TRACE_ID,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
    SPAN_PARLOT_TURN,
)
from parlot.core.ids import new_session_id
from parlot.core.sdk_version import stamp_session_sdk_version
from parlot.core.session import (
    SessionState,
    clear_active_session,
    get_active_session,
    set_active_session,
)
from parlot.core.turn_emit import stamp_turn_utterance_text

from ._platform_refs import stamp_pipecat_platform_refs
from .attrs import PIPECAT_FRAMEWORK

logger = logging.getLogger("parlot.instrumentation.pipecat")


@dataclass
class _PipecatSessionState(SessionState):
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    open_turn_index: int | None = None
    transport: str = ""
    close_emitted: bool = False


_sessions_by_conversation: dict[str, tuple[Span, _PipecatSessionState]] = {}
_configured_agent_id: str = ""
_configured_agent_version: str = ""
_tracer: Tracer | None = None
_atexit_registered = False


def set_identity(agent_id: str, version: str) -> None:
    global _configured_agent_id, _configured_agent_version
    _configured_agent_id = agent_id
    _configured_agent_version = version


def set_tracer(tracer: Tracer) -> None:
    global _tracer
    _tracer = tracer


def get_tracer() -> Tracer | None:
    return _tracer


def _ensure_atexit() -> None:
    global _atexit_registered
    if _atexit_registered:
        return
    atexit.register(flush_all_sessions)
    _atexit_registered = True


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
    existing = _sessions_by_conversation.get(conversation_id)
    if existing is not None:
        span, state = existing
        set_active_session(span, state)
        return state
    if _tracer is None:
        logger.debug("No tracer; skipping pipecat session bootstrap")
        return None

    session_id = new_session_id()
    state = _PipecatSessionState(
        session_id=session_id,
        conversation_id=conversation_id,
        framework=PIPECAT_FRAMEWORK,
        transport=transport or "",
    )
    span = _tracer.start_span(SPAN_CONVERSATION_SESSION)
    span.set_attribute(ATTR_SESSION_ID, session_id)
    span.set_attribute(ATTR_SESSION_CONVERSATION_ID, conversation_id)
    span.set_attribute(ATTR_GEN_AI_CONVERSATION_ID, conversation_id)
    _stamp_session_identity(span, conversation_id=conversation_id, state=state)
    _sessions_by_conversation[conversation_id] = (span, state)
    set_active_session(span, state)
    _ensure_atexit()
    return state


def emit_turn(
    state: _PipecatSessionState,
    *,
    turn_index: int,
    role: str = "agent",
    interrupted: bool = False,
    e2e_latency_s: float | None = None,
    utterance_text: str = "",
    start_time_ns: int | None = None,
    end_time_ns: int | None = None,
) -> str:
    """Mint a contract ``parlot.turn`` on a fresh OTel trace. Returns trace_id hex."""
    if _tracer is None:
        return ""
    state.turn_count = max(state.turn_count, turn_index)
    state.open_turn_index = turn_index

    trace_id = random.getrandbits(128)
    span_id = random.getrandbits(64)
    ctx = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(0x01),
    )
    parent_ctx = trace.set_span_in_context(NonRecordingSpan(ctx))
    start_kw: dict = {"context": parent_ctx}
    if start_time_ns is not None:
        start_kw["start_time"] = start_time_ns
    span = _tracer.start_span(SPAN_PARLOT_TURN, **start_kw)
    try:
        span.set_attribute(ATTR_SESSION_ID, state.session_id)
        span.set_attribute(ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        span.set_attribute(ATTR_GEN_AI_CONVERSATION_ID, state.conversation_id)
        span.set_attribute(ATTR_TURN_INDEX, turn_index)
        span.set_attribute(ATTR_TURN_PARTICIPANT_ROLE, role)
        span.set_attribute(ATTR_TURN_PARTICIPANT_ID, role)
        span.set_attribute(ATTR_TURN_INPUT_MODALITY, "voice")
        span.set_attribute(ATTR_AGENT_FRAMEWORK, PIPECAT_FRAMEWORK)
        if state.last_turn_trace_id:
            span.set_attribute(ATTR_TURN_PREV_TRACE_ID, state.last_turn_trace_id)
        if interrupted:
            span.set_attribute(ATTR_TURN_INTERRUPTED, True)
        if e2e_latency_s is not None:
            span.set_attribute(ATTR_TURN_E2E_LATENCY_S, float(e2e_latency_s))
        stamp_turn_utterance_text(
            span,
            participant_role=role,
            utterance_text=utterance_text,
        )
        stamp_pipecat_platform_refs(span, conversation_id=state.conversation_id)
    finally:
        if end_time_ns is not None:
            span.end(end_time=end_time_ns)
        else:
            span.end()

    tid = format(trace_id, "032x")
    state.last_turn_trace_id = tid
    return tid


def close_session(conversation_id: str, *, reason: str = "completed") -> None:
    """End the session and emit ``parlot.session.close``."""
    pair = _sessions_by_conversation.pop(conversation_id, None)
    if pair is None or _tracer is None:
        return
    session_span, state = pair
    if state.close_emitted:
        return
    state.close_emitted = True
    close = _tracer.start_span(SPAN_PARLOT_SESSION_CLOSE)
    try:
        close.set_attribute(ATTR_SESSION_ID, state.session_id)
        close.set_attribute(ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        close.set_attribute(ATTR_SESSION_CLOSE_REASON, reason)
        _stamp_session_identity(close, conversation_id=conversation_id, state=state)
    finally:
        close.end()
    try:
        session_span.set_status(Status(StatusCode.OK))
    except Exception:
        pass
    session_span.end()
    active = get_active_session()
    if active is state:
        clear_active_session()
    try:
        provider = trace.get_tracer_provider()
        force_flush = getattr(provider, "force_flush", None)
        if callable(force_flush):
            force_flush(timeout_millis=10_000)
    except Exception:
        logger.debug("force_flush after close_session failed", exc_info=True)


def flush_all_sessions() -> None:
    for conversation_id in list(_sessions_by_conversation):
        close_session(conversation_id, reason="process_exit")


def lookup_session(conversation_id: str) -> _PipecatSessionState | None:
    pair = _sessions_by_conversation.get(conversation_id)
    return pair[1] if pair else None
