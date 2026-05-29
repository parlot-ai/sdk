"""Per-job session bootstrap: ``conversation.session`` + ContextVar scope."""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_CONVERSATION_CHANNEL,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_SESSION_CLOSE_ERROR,
    ATTR_SESSION_CLOSE_REASON,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_SESSION_TURN_COUNT,
    SPAN_PARLOT_SESSION_CLOSE,
)
from parlot.core.ids import new_session_id
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
    METADATA_JOB_ID,
)
from parlot.instrumentation.livekit._platform_refs import (
    _coerce_livekit_field,
    _job_room_fields,
    register_livekit_job_context,
    stamp_livekit_platform_refs,
)

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan

    from ._processor import LiveKitGenAIProcessor, _LiveKitSessionState

logger = logging.getLogger("parlot.instrumentation.livekit")

SPAN_CONVERSATION_SESSION = "conversation.session"

_span_context_attach_enabled: bool = True

_parlot_job_bootstrap: ContextVar["_JobBootstrap | None"] = ContextVar(
    "parlot_job_bootstrap",
    default=None,
)


@dataclass
class _JobBootstrap:
    session_id: str
    session_span: Any
    state: "_LiveKitSessionState"
    processor: "LiveKitGenAIProcessor"
    attach_task: asyncio.Task | None = None
    ctx_token: Token[Context] | None = None
    aggregates_applied: bool = False
    session_span_ended: bool = False
    close_span_done: bool = False


def set_span_context_attach_enabled(enabled: bool) -> None:
    global _span_context_attach_enabled
    _span_context_attach_enabled = enabled


def get_job_bootstrap() -> _JobBootstrap | None:
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None or bootstrap.close_span_done:
        return None
    return bootstrap


def bootstrap_job_entrypoint(
    processor: "LiveKitGenAIProcessor",
    entrypoint_span: Any,
) -> None:
    """Mint session, start ``conversation.session``, set ContextVar."""
    if _parlot_job_bootstrap.get() is not None:
        logger.warning("parlot: job_entrypoint bootstrap while bootstrap already active")
    attrs = getattr(entrypoint_span, "attributes", None) or {}
    vendor_job_id = str(attrs.get(ATTR_LK_JOB_ID) or attrs.get(METADATA_JOB_ID) or "")
    room_name = str(attrs.get(ATTR_LK_ROOM_NAME) or "")
    room_sid = str(attrs.get(ATTR_LK_ROOM_SID) or "")

    from ._processor import _LiveKitSessionState

    session_id = new_session_id()
    state = _LiveKitSessionState(
        parlot_session_id=session_id,
        conversation_id=session_id,
        session_id=vendor_job_id,
        room_name=room_name,
        room_sid=room_sid,
    )
    processor._sessions[session_id] = state

    if vendor_job_id:
        register_livekit_job_context(
            vendor_job_id,
            room_name=room_name,
            room_sid=room_sid,
        )

    tracer = processor._tracer
    if tracer is None:
        logger.error("parlot: tracer not set; cannot start conversation.session")
        return

    initial_attrs = {
        ATTR_SESSION_ID: session_id,
        ATTR_SESSION_CONVERSATION_ID: session_id,
        ATTR_GEN_AI_CONVERSATION_ID: session_id,
        ATTR_CONVERSATION_CHANNEL: "voice",
    }
    if vendor_job_id:
        initial_attrs[ATTR_LK_JOB_ID] = vendor_job_id
    if room_name:
        initial_attrs[ATTR_LK_ROOM_NAME] = room_name
    if room_sid:
        initial_attrs[ATTR_LK_ROOM_SID] = room_sid

    session_span = tracer.start_span(
        SPAN_CONVERSATION_SESSION,
        attributes=initial_attrs,
    )
    stamp_livekit_platform_refs(
        session_span,
        job_id=vendor_job_id,
        room_name=room_name,
        room_sid=room_sid,
    )

    ctx_token: Token[Context] | None = None
    attach_task: asyncio.Task | None = None
    if _span_context_attach_enabled:
        try:
            attach_task = asyncio.current_task()
        except RuntimeError:
            attach_task = None
        ctx_token = otel_context.attach(trace.set_span_in_context(session_span))

    _parlot_job_bootstrap.set(
        _JobBootstrap(
            session_id=session_id,
            session_span=session_span,
            state=state,
            processor=processor,
            attach_task=attach_task,
            ctx_token=ctx_token,
        )
    )


def _finalize_session_aggregates(bootstrap: _JobBootstrap) -> None:
    if bootstrap.aggregates_applied:
        return
    bootstrap.processor._apply_root_to_live_span(bootstrap.session_span, bootstrap.state)
    bootstrap.aggregates_applied = True


def _end_session_span(bootstrap: _JobBootstrap, end_time: int | None = None) -> None:
    if bootstrap.session_span_ended:
        return
    if end_time is not None and hasattr(bootstrap.session_span, "end"):
        bootstrap.session_span.end(end_time=end_time)
    else:
        bootstrap.session_span.end()
    bootstrap.session_span_ended = True


def _flush_otlp_before_session_close(_bootstrap: _JobBootstrap) -> None:
    """Export pending spans before the close signal span."""
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if provider is None:
        return
    force_flush = getattr(provider, "force_flush", None)
    if not callable(force_flush):
        return
    timeout_ms = 5_000
    try:
        force_flush(timeout_millis=timeout_ms)
    except TypeError:
        force_flush()


def _detect_session_close_reason(entrypoint_span: "ReadableSpan") -> str:
    """Best-effort close reason from entrypoint span status."""
    status = getattr(entrypoint_span, "status", None)
    if status is not None:
        code = getattr(status, "status_code", None)
        if code is not None and str(code).endswith("ERROR"):
            message = getattr(status, "description", None) or ""
            if message:
                return "session_span_error"
            return "error"
    return "clean_close"


def emit_parlot_session_close_span(
    bootstrap: _JobBootstrap,
    *,
    end_time: int | None = None,
    close_reason: str = "clean_close",
    close_error: str | None = None,
) -> None:
    """Framework-specific hook: emit ``parlot.session.close`` for collector finalize."""
    tracer = bootstrap.processor._tracer
    if tracer is None:
        return
    state = bootstrap.state
    attrs: dict[str, object] = {
        ATTR_SESSION_ID: bootstrap.session_id,
        ATTR_SESSION_CONVERSATION_ID: state.conversation_id,
        ATTR_GEN_AI_CONVERSATION_ID: state.conversation_id,
        ATTR_AGENT_FRAMEWORK: "livekit",
        ATTR_SESSION_CLOSE_REASON: close_reason,
    }
    if close_error:
        attrs[ATTR_SESSION_CLOSE_ERROR] = close_error
    session_attrs = getattr(bootstrap.session_span, "attributes", None)
    if session_attrs is not None:
        items = (
            session_attrs.items()
            if hasattr(session_attrs, "items")
            else getattr(session_attrs, "__iter__", lambda: [])()
        )
        for key, value in items:
            if not isinstance(key, str) or key in attrs:
                continue
            if isinstance(value, (str, bool, int, float)):
                attrs[key] = value
    # Stale snapshot on conversation.session can under-report; state is authoritative.
    attrs[ATTR_SESSION_TURN_COUNT] = state.turn_count
    span = tracer.start_span(SPAN_PARLOT_SESSION_CLOSE, attributes=attrs)
    if end_time is not None and hasattr(span, "end"):
        span.end(end_time=end_time)
    else:
        span.end()


def _detach_otel_context(bootstrap: _JobBootstrap) -> None:
    """Detach only on the task that attached; otherwise drop the token reference."""
    token = bootstrap.ctx_token
    if token is None:
        return
    attach_task = bootstrap.attach_task
    try:
        current = asyncio.current_task()
    except RuntimeError:
        current = None

    if attach_task is not None and current is not attach_task:
        # AgentSession "close" often fires on a different task than job_entrypoint.
        # Detaching here would corrupt that task's context stack; the attach task
        # drops its context vars when the job ends.
        logger.debug(
            "parlot: otel context detach skipped (close on task %s, attach on %s)",
            current,
            attach_task,
        )
        return

    otel_context.detach(token)
    bootstrap.ctx_token = None


def _cleanup_job_bootstrap(
    processor: "LiveKitGenAIProcessor",
    bootstrap: _JobBootstrap,
    *,
    end_time: int | None = None,
) -> None:
    """Detach OTel context and drop in-memory session state after close is exported."""
    state = bootstrap.state
    vendor_job_id = state.session_id

    try:
        current = asyncio.current_task()
    except RuntimeError:
        current = None
    attach_task = bootstrap.attach_task
    on_attach_task = attach_task is None or attach_task is current

    if on_attach_task:
        _detach_otel_context(bootstrap)

    if not bootstrap.session_span_ended:
        _end_session_span(bootstrap, end_time=end_time)

    from parlot.instrumentation.livekit._platform_refs import clear_livekit_job_context

    if vendor_job_id:
        clear_livekit_job_context(vendor_job_id)
    processor._sessions.pop(bootstrap.session_id, None)
    if on_attach_task:
        _parlot_job_bootstrap.set(None)


def finalize_session_close_from_hook(
    bootstrap: _JobBootstrap,
    *,
    close_reason: str,
    close_error: str | None = None,
    end_time: int | None = None,
) -> None:
    """Emit ``parlot.session.close`` once when AgentSession actually closes."""
    if bootstrap.close_span_done:
        return
    _finalize_session_aggregates(bootstrap)
    _end_session_span(bootstrap, end_time=end_time)
    _flush_otlp_before_session_close(bootstrap)
    emit_parlot_session_close_span(
        bootstrap,
        end_time=end_time,
        close_reason=close_reason,
        close_error=close_error,
    )
    # Mark closed before cleanup so other tasks still holding this ContextVar
    # value stop resolving session attributes (close hook != attach task).
    bootstrap.close_span_done = True
    _cleanup_job_bootstrap(bootstrap.processor, bootstrap, end_time=end_time)


def teardown_job_entrypoint(processor: "LiveKitGenAIProcessor", entrypoint_span: "ReadableSpan") -> None:
    """Job span ended — only tear down if session close already ran via AgentSession hook."""
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None:
        return

    if not bootstrap.close_span_done:
        # LiveKit may end the job_entrypoint span before the voice session finishes.
        # Keep bootstrap alive so turns keep resolving and the close hook can fire once.
        logger.debug(
            "parlot: job_entrypoint span ended before AgentSession close; deferring teardown"
        )
        return

    state = bootstrap.state
    vendor_job_id = state.session_id
    if vendor_job_id and not state.room_sid:
        from parlot.instrumentation.livekit._platform_refs import lookup_room_context

        rn, rs = lookup_room_context(vendor_job_id)
        if rn:
            state.room_name = rn
        if rs:
            state.room_sid = rs

    _cleanup_job_bootstrap(
        processor,
        bootstrap,
        end_time=getattr(entrypoint_span, "end_time", None),
    )


def handle_conversation_session_on_end() -> None:
    """Apply close-time aggregates if OTel ends the session span before teardown."""
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None:
        return
    if hasattr(bootstrap.session_span, "is_recording"):
        if not bootstrap.session_span.is_recording():
            bootstrap.session_span_ended = True
    else:
        bootstrap.session_span_ended = True
    if not bootstrap.aggregates_applied:
        logger.debug(
            "parlot: conversation.session ended before job_entrypoint teardown; "
            "applying session aggregates early"
        )
        _finalize_session_aggregates(bootstrap)


async def refresh_bootstrap_room_from_ctx(ctx) -> None:
    """After ``JobContext.connect``, stamp room_sid on the live session span."""
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None:
        return

    job_id, room_name, room_sid = _job_room_fields(ctx)
    if not room_sid and getattr(ctx, "_connected", False):
        room = getattr(ctx, "room", None)
        room_sid = await _coerce_livekit_field(room, "sid", "id")
        if not room_name:
            room_name = await _coerce_livekit_field(room, "name")

    state = bootstrap.state
    if room_name:
        state.room_name = room_name
    if room_sid:
        state.room_sid = room_sid

    vendor_job_id = state.session_id or job_id
    if vendor_job_id:
        register_livekit_job_context(
            vendor_job_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )

    session_span = bootstrap.session_span
    if session_span is not None and hasattr(session_span, "is_recording"):
        if not session_span.is_recording():
            return
        if room_sid:
            session_span.set_attribute(ATTR_LK_ROOM_SID, room_sid)
        if room_name:
            session_span.set_attribute(ATTR_LK_ROOM_NAME, room_name)
        stamp_livekit_platform_refs(
            session_span,
            job_id=vendor_job_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )
