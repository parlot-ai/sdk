"""Per-job session bootstrap: ``parlot.session`` + ContextVar scope."""

from __future__ import annotations

import asyncio
import logging
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
    ATTR_SESSION_TOTAL_INPUT_TOKENS,
    ATTR_SESSION_TOTAL_OUTPUT_TOKENS,
    ATTR_SESSION_TURN_COUNT,
    ATTR_SESSION_TURN_INDEX_MAX,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
)
from parlot.core.ids import new_session_id
from parlot.core.metadata import stamp_session_metadata_attrs
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_AGENT_NAME,
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
)
from parlot.instrumentation.livekit._agent_identity import stamp_session_agent_identity
from parlot.core.sdk_version import stamp_session_sdk_version
from parlot.instrumentation.livekit._recording_guard import agent_name_from_ctx
from parlot.instrumentation.livekit._platform_refs import (
    _coerce_livekit_field,
    _job_room_fields,
    register_livekit_job_context,
    stamp_livekit_platform_refs,
)

if TYPE_CHECKING:
    from ._processor import LiveKitGenAIProcessor
    from ._session_state import _LiveKitSessionState

logger = logging.getLogger("parlot.instrumentation.livekit")

_span_context_attach_enabled: bool = True

_parlot_job_bootstrap: ContextVar["_JobBootstrap | None"] = ContextVar(
    "parlot_job_bootstrap",
    default=None,
)

# Job-scoped fallback when ContextVar is not visible (async task / OTEL context isolation).
_vendor_job_bootstraps: dict[str, "_JobBootstrap"] = {}

# Closed-session correlation for post-close evaluation LLM spans (JudgeGroup).
# Never substitutes for an active bootstrap — cleared on next bootstrap / TTL.
_STICKY_TTL_S = 30 * 60


@dataclass(frozen=True)
class _StickyClosedSession:
    session_id: str
    conversation_id: str
    closed_at: float  # time.monotonic()


_sticky_closed_sessions: dict[str, _StickyClosedSession] = {}


def clear_sticky_closed_session(vendor_job_id: str) -> None:
    """Drop sticky entry for a job (call before minting a new session)."""
    jid = str(vendor_job_id or "").strip()
    if jid:
        _sticky_closed_sessions.pop(jid, None)


def remember_sticky_closed_session(
    vendor_job_id: str,
    *,
    session_id: str,
    conversation_id: str,
) -> None:
    """Retain closed session ids for late evaluation enrich (survives bootstrap cleanup)."""
    jid = str(vendor_job_id or "").strip()
    sid = str(session_id or "").strip()
    if not jid or not sid:
        return
    _sticky_closed_sessions[jid] = _StickyClosedSession(
        session_id=sid,
        conversation_id=str(conversation_id or sid).strip() or sid,
        closed_at=time.monotonic(),
    )


def get_sticky_closed_session(vendor_job_id: str) -> _StickyClosedSession | None:
    """Return sticky closed session for job_id if present and not expired."""
    jid = str(vendor_job_id or "").strip()
    if not jid:
        return None
    sticky = _sticky_closed_sessions.get(jid)
    if sticky is None:
        return None
    if time.monotonic() - sticky.closed_at > _STICKY_TTL_S:
        _sticky_closed_sessions.pop(jid, None)
        return None
    return sticky


def clear_all_sticky_closed_sessions() -> None:
    """Test / process-shutdown helper."""
    _sticky_closed_sessions.clear()


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


def _bootstrap_for_vendor_job_id(vendor_job_id: str) -> _JobBootstrap | None:
    bootstrap = _vendor_job_bootstraps.get(vendor_job_id)
    if bootstrap is None or bootstrap.close_span_done:
        return None
    return bootstrap


def get_job_bootstrap() -> _JobBootstrap | None:
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is not None and not bootstrap.close_span_done:
        return bootstrap
    try:
        from livekit.agents.job import get_job_context

        ctx = get_job_context()
        if ctx is not None:
            return _bootstrap_for_vendor_job_id(str(ctx.job.id))
    except Exception:
        pass
    return None


def bootstrap_session(
    processor: "LiveKitGenAIProcessor",
    *,
    vendor_job_id: str = "",
    room_name: str = "",
    room_sid: str = "",
    worker_agent_name: str = "",
) -> None:
    """Mint session, start ``parlot.session``, set ContextVar."""
    existing = _parlot_job_bootstrap.get()
    if existing is not None and not existing.close_span_done:
        logger.debug("parlot: bootstrap_session skipped — bootstrap already active")
        return

    vendor_job_id = str(vendor_job_id or "").strip()
    room_name = str(room_name or "").strip()
    room_sid = str(room_sid or "").strip()
    worker_agent_name = str(worker_agent_name or "").strip()

    # Isolation: never let a prior closed session's sticky id leak into a new one.
    if vendor_job_id:
        clear_sticky_closed_session(vendor_job_id)

    from ._session_state import _LiveKitSessionState

    session_id = new_session_id()
    state = _LiveKitSessionState(
        parlot_session_id=session_id,
        # LiveKit voice intentionally uses 1:1 conversation_id===session_id as a
        # placeholder until multi-session conversations are modeled.
        conversation_id=session_id,
        session_id=vendor_job_id,
        room_name=room_name,
        room_sid=room_sid,
        worker_agent_name=worker_agent_name,
    )
    processor._sessions[session_id] = state
    if vendor_job_id:
        processor._sessions[vendor_job_id] = state

    if vendor_job_id:
        register_livekit_job_context(
            vendor_job_id,
            room_name=room_name,
            room_sid=room_sid,
        )

    tracer = processor._tracer
    if tracer is None:
        logger.error("parlot: tracer not set; cannot start parlot.session")
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
    if worker_agent_name:
        initial_attrs[ATTR_LK_AGENT_NAME] = worker_agent_name

    session_span = tracer.start_span(
        SPAN_CONVERSATION_SESSION,
        attributes=initial_attrs,
    )
    stamp_session_agent_identity(session_span, state)
    stamp_session_sdk_version(session_span)
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

    bootstrap = _JobBootstrap(
        session_id=session_id,
        session_span=session_span,
        state=state,
        processor=processor,
        attach_task=attach_task,
        ctx_token=ctx_token,
    )
    _parlot_job_bootstrap.set(bootstrap)
    if vendor_job_id:
        _vendor_job_bootstraps[vendor_job_id] = bootstrap

    from parlot.core.session import set_active_session

    state.framework = "livekit"
    set_active_session(session_span, state)


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


# Close-path flush budget (~12s wall from AgentSession close) with short backoff.
_CLOSE_FLUSH_BUDGET_S = 12.0
_CLOSE_FLUSH_BACKOFFS_S = (1.0, 3.0, 6.0)
_CLOSE_FLUSH_ATTEMPT_TIMEOUT_MS = 4_000
CLOSE_ERROR_OTLP_FLUSH_INCOMPLETE = "otlp_flush_incomplete"


def _force_flush_tracer_provider(*, timeout_millis: int) -> bool:
    """Return True when the tracer provider reports a successful flush."""
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if provider is None:
        return True
    force_flush = getattr(provider, "force_flush", None)
    if not callable(force_flush):
        return True
    try:
        result = force_flush(timeout_millis=timeout_millis)
    except TypeError:
        result = force_flush()
    except Exception:
        logger.warning("parlot: force_flush raised before session close", exc_info=True)
        return False
    if result is None:
        # Some providers return None on success; treat as ok.
        return True
    return bool(result)


def _flush_otlp_before_session_close(_bootstrap: _JobBootstrap) -> bool:
    """Retry OTLP flush before emitting ``parlot.session.close``.

    Returns True when flush confirmed within the close budget; False otherwise.
    Backoffs are 1s / 3s / 6s inside a ~12s wall-clock budget shared with ingest.
    """
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        remaining_s = _CLOSE_FLUSH_BUDGET_S - (time.monotonic() - started)
        if remaining_s <= 0:
            break
        timeout_ms = min(
            _CLOSE_FLUSH_ATTEMPT_TIMEOUT_MS,
            max(1, int(remaining_s * 1000)),
        )
        ok = _force_flush_tracer_provider(timeout_millis=timeout_ms)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if ok:
            logger.info(
                "parlot: otlp flush before close ok attempts=%s elapsed_ms=%s",
                attempt,
                elapsed_ms,
            )
            return True
        backoff_idx = attempt - 1
        if backoff_idx >= len(_CLOSE_FLUSH_BACKOFFS_S):
            break
        backoff_s = _CLOSE_FLUSH_BACKOFFS_S[backoff_idx]
        remaining_s = _CLOSE_FLUSH_BUDGET_S - (time.monotonic() - started)
        if remaining_s <= 0:
            break
        sleep_s = min(backoff_s, remaining_s)
        logger.warning(
            "parlot: otlp flush before close incomplete; retrying "
            "attempt=%s sleep_s=%.1f remaining_s=%.1f",
            attempt,
            sleep_s,
            remaining_s,
        )
        time.sleep(sleep_s)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.warning(
        "parlot: otlp flush before close failed attempts=%s elapsed_ms=%s",
        attempt,
        elapsed_ms,
    )
    return False


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
    attrs: dict[str, Any] = {
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
    # Stale snapshot on parlot.session can under-report; state is authoritative.
    attrs[ATTR_SESSION_TURN_COUNT] = state.turn_count
    attrs[ATTR_SESSION_TURN_INDEX_MAX] = state.turn_count
    attrs[ATTR_SESSION_TOTAL_INPUT_TOKENS] = state.total_input_tokens
    attrs[ATTR_SESSION_TOTAL_OUTPUT_TOKENS] = state.total_output_tokens
    stamp_session_metadata_attrs(attrs, getattr(state, "custom_metadata", None))
    span = tracer.start_span(SPAN_PARLOT_SESSION_CLOSE, attributes=attrs)
    stamp_session_sdk_version(span, state)
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
        # AgentSession "close" often fires on a different task than bootstrap attach.
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
        _vendor_job_bootstraps.pop(vendor_job_id, None)
        processor._sessions.pop(vendor_job_id, None)
    processor._sessions.pop(bootstrap.session_id, None)
    if on_attach_task:
        _parlot_job_bootstrap.set(None)

    from parlot.core.session import clear_active_session

    clear_active_session()


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
    flush_ok = _flush_otlp_before_session_close(bootstrap)
    resolved_close_error = close_error
    if not flush_ok:
        # Prefer an existing close_error from the framework; otherwise stamp flush miss.
        resolved_close_error = close_error or CLOSE_ERROR_OTLP_FLUSH_INCOMPLETE
    emit_parlot_session_close_span(
        bootstrap,
        end_time=end_time,
        close_reason=close_reason,
        close_error=resolved_close_error,
    )
    # Mark closed before cleanup so other tasks still holding this ContextVar
    # value stop resolving session attributes (close hook != attach task).
    bootstrap.close_span_done = True
    if bootstrap.state.parlot_session_id:
        from ._telemetry_compare import get_compare_logger

        get_compare_logger().finalize_session(bootstrap.state.parlot_session_id)
    # Remember closed session for post-close JudgeGroup LLM spans before cleanup.
    vendor_job_id = str(bootstrap.state.session_id or "").strip()
    if vendor_job_id and bootstrap.session_id:
        remember_sticky_closed_session(
            vendor_job_id,
            session_id=bootstrap.session_id,
            conversation_id=bootstrap.state.conversation_id or bootstrap.session_id,
        )
    _cleanup_job_bootstrap(bootstrap.processor, bootstrap, end_time=end_time)


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
            "parlot: parlot.session ended before AgentSession close; "
            "applying session aggregates early"
        )
        _finalize_session_aggregates(bootstrap)


async def _run_post_bootstrap_connect(ctx: Any) -> None:
    """Refresh room metadata and start egress after session bootstrap."""
    if get_job_bootstrap() is None:
        return
    await refresh_bootstrap_room_from_ctx(ctx)
    from ._egress import maybe_start_room_composite_egress

    await maybe_start_room_composite_egress(ctx)


def schedule_post_bootstrap_connect(ctx: Any) -> None:
    """Schedule connect side effects after event-based bootstrap."""
    if ctx is None:
        logger.warning("parlot: post-bootstrap connect skipped — no JobContext")
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "parlot: post-bootstrap connect skipped — no running event loop"
        )
        return
    loop.create_task(_run_post_bootstrap_connect(ctx))


async def refresh_bootstrap_room_from_ctx(ctx) -> None:
    """After ``JobContext.connect``, stamp room_sid on the live session span."""
    bootstrap = _parlot_job_bootstrap.get()
    if bootstrap is None:
        return

    job_id, room_name, room_sid = _job_room_fields(ctx)
    state = bootstrap.state
    worker_agent_name = agent_name_from_ctx(ctx)
    if worker_agent_name:
        state.worker_agent_name = worker_agent_name
    if not room_sid and getattr(ctx, "_connected", False):
        room = getattr(ctx, "room", None)
        room_sid = await _coerce_livekit_field(room, "sid", "id")
        if not room_name:
            room_name = await _coerce_livekit_field(room, "name")

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
        if worker_agent_name:
            session_span.set_attribute(ATTR_LK_AGENT_NAME, worker_agent_name)
        stamp_session_agent_identity(session_span, state)
        stamp_session_sdk_version(session_span)
        stamp_livekit_platform_refs(
            session_span,
            job_id=vendor_job_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )
