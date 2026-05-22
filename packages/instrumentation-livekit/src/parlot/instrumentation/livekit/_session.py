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

from parlot.core.attrs import ATTR_GEN_AI_CONVERSATION_ID, ATTR_SESSION_CONVERSATION_ID, ATTR_SESSION_ID
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

# When False (ConcurrentMultiSpanProcessor), skip context.attach for trace parenting.
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
    attach_task: asyncio.Task | None = None
    ctx_token: Token[Context] | None = None
    session_span_ended: bool = False


def set_span_context_attach_enabled(enabled: bool) -> None:
    global _span_context_attach_enabled
    _span_context_attach_enabled = enabled


def get_job_bootstrap() -> _JobBootstrap | None:
    return _parlot_job_bootstrap.get()


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
    }
    if vendor_job_id:
        initial_attrs[ATTR_LK_JOB_ID] = vendor_job_id
    if room_name:
        initial_attrs[ATTR_LK_ROOM_NAME] = room_name
    if room_sid:
        initial_attrs[ATTR_LK_ROOM_SID] = room_sid

    parent_ctx = trace.set_span_in_context(entrypoint_span)
    session_span = tracer.start_span(
        SPAN_CONVERSATION_SESSION,
        context=parent_ctx,
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
            attach_task=attach_task,
            ctx_token=ctx_token,
        )
    )


def teardown_job_entrypoint(processor: "LiveKitGenAIProcessor", entrypoint_span: "ReadableSpan") -> None:
    """End ``conversation.session``, detach context, clear bootstrap."""
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None:
        logger.error("parlot: job_entrypoint on_end without active bootstrap")
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

    processor._apply_root_to_live_span(bootstrap.session_span, state)

    end_time = getattr(entrypoint_span, "end_time", None)
    if bootstrap.ctx_token is not None:
        if bootstrap.attach_task is not None:
            try:
                if bootstrap.attach_task is not asyncio.current_task():
                    raise AssertionError(
                        "parlot: ctx detach must run on the same asyncio Task as attach"
                    )
            except RuntimeError:
                pass
        otel_context.detach(bootstrap.ctx_token)

    if not bootstrap.session_span_ended:
        if end_time is not None and hasattr(bootstrap.session_span, "end"):
            bootstrap.session_span.end(end_time=end_time)
        else:
            bootstrap.session_span.end()
        bootstrap.session_span_ended = True

    from parlot.instrumentation.livekit._platform_refs import clear_livekit_job_context

    if vendor_job_id:
        clear_livekit_job_context(vendor_job_id)
    processor._sessions.pop(bootstrap.session_id, None)
    _parlot_job_bootstrap.set(None)


def handle_conversation_session_on_end() -> None:
    """Assert we own ``conversation.session`` lifecycle."""
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None:
        return
    if not bootstrap.session_span_ended:
        raise AssertionError(
            "parlot: conversation.session ended before job_entrypoint teardown"
        )


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
