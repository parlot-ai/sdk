"""thread_id → parlot.session / parlot.turn when LangGraph owns the session."""

from __future__ import annotations

import atexit
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_CONVERSATION_CHANNEL,
    ATTR_GEN_AI_AGENT_ID,
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID,
    ATTR_SESSION_AGENT_ID,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_SESSION_MODALITY,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_PARTICIPANT_ROLE,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
    SPAN_PARLOT_TURN,
)
from parlot.core.ids import new_session_id
from parlot.core.turn_emit import stamp_turn_utterance_text
from parlot.core.session import (
    SessionState,
    clear_active_session,
    get_active_session,
    session_owned,
    set_active_session,
)
from parlot.instrumentation.langgraph.attrs import ATTR_LG_THREAD_ID

logger = logging.getLogger("parlot.instrumentation.langgraph")

LANGGRAPH_FRAMEWORK = "langgraph"
_TEXT_CHANNELS = frozenset({"webchat", "sms", "whatsapp"})


@dataclass
class _LangGraphSessionState(SessionState):
    thread_id: str = ""
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    open_root_runs: set[str] = field(default_factory=set)
    open_agent_turn_index: int | None = None


_sessions_by_thread: dict[str, tuple[Span, _LangGraphSessionState]] = {}
_configured_agent_id: str = ""
_configured_agent_version: str = ""
_configured_channel: str = ""
_configured_modality: str = ""
_tracer: Tracer | None = None
_atexit_registered = False


def set_identity(agent_id: str, version: str) -> None:
    global _configured_agent_id, _configured_agent_version
    _configured_agent_id = agent_id
    _configured_agent_version = version


def set_channel_modality(*, channel: str = "", modality: str = "") -> None:
    """Transport hints for LangGraph-owned sessions (ignored under LiveKit)."""
    global _configured_channel, _configured_modality
    _configured_channel = (channel or "").strip()
    _configured_modality = (modality or "").strip()


def set_tracer(tracer: Tracer) -> None:
    global _tracer
    _tracer = tracer


def livekit_owns_session() -> bool:
    """True when LiveKit instrumentation already bound an active session."""
    if session_owned(framework="livekit"):
        return True
    state = get_active_session()
    # LiveKit sets framework on bootstrap; also accept session without framework
    # only when agent.framework was stamped livekit elsewhere — prefer explicit.
    return bool(state and state.framework == "livekit")


def _resolved_modality() -> str:
    if _configured_modality:
        return _configured_modality
    if _configured_channel == "voice":
        return "voice"
    if _configured_channel in _TEXT_CHANNELS:
        return "text"
    return ""


def _ensure_atexit() -> None:
    global _atexit_registered
    if _atexit_registered:
        return
    atexit.register(flush_all_sessions)
    _atexit_registered = True


def _stamp_session_identity(span: Span, *, thread_id: str) -> None:
    span.set_attribute(ATTR_AGENT_FRAMEWORK, LANGGRAPH_FRAMEWORK)
    span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK, LANGGRAPH_FRAMEWORK)
    # Channel/modality are transport concerns — not implied by LangGraph.
    # LiveKit-owned sessions never reach here; standalone agents should pass
    # channel= (and optionally modality=) to configure().
    if _configured_channel:
        span.set_attribute(ATTR_CONVERSATION_CHANNEL, _configured_channel)
    modality = _resolved_modality()
    if modality:
        span.set_attribute(ATTR_SESSION_MODALITY, modality)
    span.set_attribute(ATTR_LG_THREAD_ID, thread_id)
    if _configured_agent_id:
        span.set_attribute(ATTR_GEN_AI_AGENT_ID, _configured_agent_id)
        span.set_attribute(ATTR_SESSION_AGENT_ID, _configured_agent_id)
        span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID, _configured_agent_id)
    if _configured_agent_version:
        span.set_attribute(ATTR_GEN_AI_AGENT_VERSION, _configured_agent_version)


def ensure_session(thread_id: str) -> _LangGraphSessionState | None:
    """Open or return a session for ``thread_id``. No-op when LiveKit owns session."""
    if livekit_owns_session():
        return None
    if not thread_id:
        thread_id = f"anon-{uuid.uuid4().hex[:12]}"
    existing = _sessions_by_thread.get(thread_id)
    if existing is not None:
        span, state = existing
        set_active_session(span, state)
        return state
    if _tracer is None:
        logger.debug("No tracer; skipping langgraph session bootstrap")
        return None

    session_id = new_session_id()
    conversation_id = thread_id
    state = _LangGraphSessionState(
        session_id=session_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        framework=LANGGRAPH_FRAMEWORK,
    )
    span = _tracer.start_span(SPAN_CONVERSATION_SESSION)
    span.set_attribute(ATTR_SESSION_ID, session_id)
    span.set_attribute(ATTR_SESSION_CONVERSATION_ID, conversation_id)
    span.set_attribute(ATTR_GEN_AI_CONVERSATION_ID, conversation_id)
    _stamp_session_identity(span, thread_id=thread_id)
    _sessions_by_thread[thread_id] = (span, state)
    set_active_session(span, state)
    _ensure_atexit()
    return state


def emit_turn(
    state: _LangGraphSessionState,
    *,
    role: str,
    turn_index: int | None = None,
    utterance_text: str = "",
) -> int:
    if livekit_owns_session() or _tracer is None:
        return turn_index or state.turn_count
    if turn_index is None:
        state.turn_count += 1
        turn_index = state.turn_count
    else:
        state.turn_count = max(state.turn_count, turn_index)

    import random

    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    trace_id = random.getrandbits(128)
    span_id = random.getrandbits(64)
    ctx = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(0x01),
    )
    parent_ctx = trace.set_span_in_context(NonRecordingSpan(ctx))
    span = _tracer.start_span(SPAN_PARLOT_TURN, context=parent_ctx)
    try:
        span.set_attribute(ATTR_SESSION_ID, state.session_id)
        span.set_attribute(ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        span.set_attribute(ATTR_GEN_AI_CONVERSATION_ID, state.conversation_id)
        span.set_attribute(ATTR_TURN_INDEX, turn_index)
        span.set_attribute(ATTR_TURN_PARTICIPANT_ROLE, role)
        modality = _resolved_modality()
        if modality:
            span.set_attribute(ATTR_TURN_INPUT_MODALITY, modality)
        span.set_attribute(ATTR_AGENT_FRAMEWORK, LANGGRAPH_FRAMEWORK)
        span.set_attribute(ATTR_LG_THREAD_ID, state.thread_id)
        stamp_turn_utterance_text(
            span,
            participant_role=role,
            utterance_text=utterance_text,
        )
    finally:
        span.end()
    state.last_turn_trace_id = format(trace_id, "032x")
    return turn_index


def close_session(thread_id: str, *, reason: str = "completed") -> None:
    """End the session for ``thread_id`` and emit ``parlot.session.close``."""
    pair = _sessions_by_thread.pop(thread_id, None)
    if pair is None or _tracer is None:
        return
    session_span, state = pair
    close = _tracer.start_span(SPAN_PARLOT_SESSION_CLOSE)
    try:
        close.set_attribute(ATTR_SESSION_ID, state.session_id)
        close.set_attribute(ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        close.set_attribute("session.close_reason", reason)
        _stamp_session_identity(close, thread_id=thread_id)
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
    # BatchSpanProcessor otherwise may exit before GenAI/contract spans export.
    try:
        provider = trace.get_tracer_provider()
        force_flush = getattr(provider, "force_flush", None)
        if callable(force_flush):
            force_flush(timeout_millis=10_000)
    except Exception:
        logger.debug("force_flush after close_session failed", exc_info=True)


def flush_all_sessions() -> None:
    for thread_id in list(_sessions_by_thread):
        close_session(thread_id, reason="process_exit")


def thread_id_from_metadata(metadata: dict[str, Any] | None, tags: list[str] | None = None) -> str:
    meta = metadata or {}
    for key in ("thread_id", "session_id", "conversation_id"):
        val = meta.get(key)
        if val:
            return str(val)
    configurable = meta.get("configurable")
    if isinstance(configurable, dict) and configurable.get("thread_id"):
        return str(configurable["thread_id"])
    return ""
