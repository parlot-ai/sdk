"""thread_id → parlot.session / parlot.turn when LangGraph owns the session."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

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
)
from parlot.core.sdk_version import stamp_session_sdk_version
from parlot.core.session import (
    SessionState,
    get_active_session,
    session_owned,
)
from parlot.core.session_lifecycle import (
    emit_parlot_session_close,
    force_flush_tracer_provider,
    start_parlot_session_span,
)
from parlot.core.session_registry import ConversationSessionRegistry
from parlot.core.turn_emit import emit_parlot_turn_root
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


_registry: ConversationSessionRegistry[_LangGraphSessionState] = (
    ConversationSessionRegistry()
)
# Backward-compat alias for tests that clear the session map directly.
_sessions_by_thread = _registry._sessions
_configured_agent_id: str = ""
_configured_agent_version: str = ""
_configured_channel: str = ""
_configured_modality: str = ""
_tracer: Tracer | None = None


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


def _stamp_session_identity(span: Span, *, thread_id: str, state: Any | None = None) -> None:
    span.set_attribute(ATTR_AGENT_FRAMEWORK, LANGGRAPH_FRAMEWORK)
    span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK, LANGGRAPH_FRAMEWORK)
    # Channel/modality are transport concerns — not implied by LangGraph.
    # LiveKit-owned sessions never reach here; standalone agents should pass
    # channel= (and optionally modality=) to parlotize().
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
    stamp_session_sdk_version(span, state)


def ensure_session(thread_id: str) -> _LangGraphSessionState | None:
    """Open or return a session for ``thread_id``. No-op when LiveKit owns session."""
    if livekit_owns_session():
        return None
    if not thread_id:
        thread_id = f"anon-{uuid.uuid4().hex[:12]}"

    tid = thread_id

    def _factory() -> tuple[Span, _LangGraphSessionState] | None:
        if _tracer is None:
            logger.debug("No tracer; skipping langgraph session bootstrap")
            return None
        conversation_id = tid
        state = _LangGraphSessionState(
            session_id="",
            conversation_id=conversation_id,
            thread_id=tid,
            framework=LANGGRAPH_FRAMEWORK,
        )

        def _stamp(span: Span) -> None:
            _stamp_session_identity(span, thread_id=tid, state=state)

        span, session_id = start_parlot_session_span(
            _tracer,
            conversation_id=conversation_id,
            stamp_fn=_stamp,
        )
        state.session_id = session_id
        return span, state

    state = _registry.ensure(tid, _factory)
    if state is not None:
        _registry.ensure_atexit(flush_all_sessions)
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

    extra: dict[str, Any] = {
        ATTR_AGENT_FRAMEWORK: LANGGRAPH_FRAMEWORK,
        ATTR_LG_THREAD_ID: state.thread_id,
    }
    modality = _resolved_modality()
    if modality:
        extra[ATTR_TURN_INPUT_MODALITY] = modality

    tid, _span_id = emit_parlot_turn_root(
        _tracer,
        session_id=state.session_id,
        conversation_id=state.conversation_id,
        turn_index=turn_index,
        participant_role=role,
        utterance_text=utterance_text,
        stamp_genai_conversation_id=True,
        extra_attrs=extra,
    )
    state.last_turn_trace_id = tid
    return turn_index


def close_session(thread_id: str, *, reason: str = "completed") -> None:
    """End the session for ``thread_id`` and emit ``parlot.session.close``."""
    if _tracer is None:
        _registry.pop(thread_id)
        return

    def _closer(session_span: Span, state: _LangGraphSessionState) -> None:
        emit_parlot_session_close(
            _tracer,
            session_id=state.session_id,
            conversation_id=state.conversation_id,
            reason=reason,
            framework=LANGGRAPH_FRAMEWORK,
            stamp_fn=lambda span: _stamp_session_identity(
                span, thread_id=thread_id, state=state
            ),
            state=state,
        )
        _registry.end_and_clear(session_span, state)
        if not force_flush_tracer_provider(timeout_millis=10_000):
            logger.debug("force_flush after close_session failed")

    _registry.close(thread_id, closer=_closer, clear_active=False)


def flush_all_sessions() -> None:
    _registry.flush_all(
        lambda thread_id: close_session(thread_id, reason="process_exit")
    )


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
