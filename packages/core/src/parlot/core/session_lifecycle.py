"""Shared session open/close and OTLP flush helpers for instrumentation adapters."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Mapping, Sequence

from opentelemetry.trace import Status, StatusCode

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_SESSION_CLOSE_ERROR,
    ATTR_SESSION_CLOSE_REASON,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
)
from parlot.core.ids import new_session_id
from parlot.core.sdk_version import stamp_session_sdk_version

logger = logging.getLogger("parlot.core.session_lifecycle")

# LiveKit close-path defaults (~12s wall with short backoff).
DEFAULT_CLOSE_FLUSH_BUDGET_S = 12.0
DEFAULT_CLOSE_FLUSH_BACKOFFS_S: tuple[float, ...] = (1.0, 3.0, 6.0)
DEFAULT_CLOSE_FLUSH_ATTEMPT_TIMEOUT_MS = 4_000


def force_flush_tracer_provider(
    provider: Any | None = None,
    *,
    timeout_millis: int = 10_000,
) -> bool:
    """Return True when the tracer provider reports a successful flush.

    When ``provider`` is omitted, uses the global tracer provider.
    """
    if provider is None:
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
        try:
            result = force_flush()
        except Exception:
            logger.warning("parlot: force_flush raised", exc_info=True)
            return False
    except Exception:
        logger.warning("parlot: force_flush raised", exc_info=True)
        return False
    if result is None:
        # Some providers return None on success; treat as ok.
        return True
    return bool(result)


def force_flush_with_budget(
    *,
    budget_s: float = DEFAULT_CLOSE_FLUSH_BUDGET_S,
    backoffs_s: Sequence[float] = DEFAULT_CLOSE_FLUSH_BACKOFFS_S,
    attempt_timeout_ms: int = DEFAULT_CLOSE_FLUSH_ATTEMPT_TIMEOUT_MS,
    provider: Any | None = None,
    flush_fn: Callable[..., bool] | None = None,
    log: logging.Logger | None = None,
) -> bool:
    """Retry OTLP flush within a wall-clock budget.

    Returns True when flush confirmed within the budget; False otherwise.
    Default policy matches LiveKit's Room Composite close path (1s/3s/6s
    backoff inside ~12s).

    ``flush_fn`` defaults to :func:`force_flush_tracer_provider`. Adapters may
    pass a local wrapper so tests can patch the adapter module symbol.
    """
    log = log or logger
    do_flush = flush_fn or (
        lambda *, timeout_millis: force_flush_tracer_provider(
            provider, timeout_millis=timeout_millis
        )
    )
    started = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        remaining_s = budget_s - (time.monotonic() - started)
        if remaining_s <= 0:
            break
        timeout_ms = min(attempt_timeout_ms, max(1, int(remaining_s * 1000)))
        ok = do_flush(timeout_millis=timeout_ms)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if ok:
            log.info(
                "parlot: otlp flush before close ok attempts=%s elapsed_ms=%s",
                attempt,
                elapsed_ms,
            )
            return True
        backoff_idx = attempt - 1
        if backoff_idx >= len(backoffs_s):
            break
        backoff_s = backoffs_s[backoff_idx]
        remaining_s = budget_s - (time.monotonic() - started)
        if remaining_s <= 0:
            break
        sleep_s = min(backoff_s, remaining_s)
        log.warning(
            "parlot: otlp flush before close incomplete; retrying "
            "attempt=%s sleep_s=%.1f remaining_s=%.1f",
            attempt,
            sleep_s,
            remaining_s,
        )
        time.sleep(sleep_s)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.warning(
        "parlot: otlp flush before close failed attempts=%s elapsed_ms=%s",
        attempt,
        elapsed_ms,
    )
    return False


def _copy_scalar_attrs_from_span(
    source_span: Any,
    attrs: dict[str, Any],
) -> None:
    session_attrs = getattr(source_span, "attributes", None)
    if session_attrs is None:
        return
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


def emit_parlot_session_close(
    tracer: Any,
    *,
    session_id: str,
    conversation_id: str,
    reason: str = "completed",
    framework: str = "",
    close_error: str | None = None,
    extra_attrs: Mapping[str, Any] | None = None,
    copy_from_session_span: Any | None = None,
    stamp_fn: Callable[[Any], None] | None = None,
    end_time: int | None = None,
    state: Any | None = None,
) -> None:
    """Mint a ``parlot.session.close`` span for collector finalize.

    ``stamp_fn`` applies framework identity / platform refs after base attrs.
    ``copy_from_session_span`` copies scalar attrs from the live session span
    (LiveKit uses this so close carries room/job metadata).
    """
    if tracer is None:
        return
    attrs: dict[str, Any] = {
        ATTR_SESSION_ID: session_id,
        ATTR_SESSION_CONVERSATION_ID: conversation_id,
        ATTR_SESSION_CLOSE_REASON: reason,
    }
    if conversation_id:
        attrs[ATTR_GEN_AI_CONVERSATION_ID] = conversation_id
    if framework:
        attrs[ATTR_AGENT_FRAMEWORK] = framework
    if close_error:
        attrs[ATTR_SESSION_CLOSE_ERROR] = close_error
    if copy_from_session_span is not None:
        _copy_scalar_attrs_from_span(copy_from_session_span, attrs)
    if extra_attrs:
        for key, value in extra_attrs.items():
            if value is None:
                continue
            attrs[key] = value

    span = tracer.start_span(SPAN_PARLOT_SESSION_CLOSE, attributes=attrs)
    try:
        if stamp_fn is not None:
            stamp_fn(span)
        if state is not None:
            stamp_session_sdk_version(span, state)
    finally:
        if end_time is not None and hasattr(span, "end"):
            span.end(end_time=end_time)
        else:
            span.end()


def start_parlot_session_span(
    tracer: Any,
    *,
    session_id: str | None = None,
    conversation_id: str,
    stamp_fn: Callable[[Any], None] | None = None,
    extra_attrs: Mapping[str, Any] | None = None,
) -> tuple[Any, str]:
    """Start a ``parlot.session`` span and stamp identity.

    Returns ``(span, session_id)``. Generates a session id when omitted.
    """
    sid = session_id or new_session_id()
    span = tracer.start_span(SPAN_CONVERSATION_SESSION)
    span.set_attribute(ATTR_SESSION_ID, sid)
    span.set_attribute(ATTR_SESSION_CONVERSATION_ID, conversation_id)
    span.set_attribute(ATTR_GEN_AI_CONVERSATION_ID, conversation_id)
    if extra_attrs:
        for key, value in extra_attrs.items():
            if value is None or value == "":
                continue
            span.set_attribute(key, value)
    if stamp_fn is not None:
        stamp_fn(span)
    return span, sid


def end_session_span_ok(session_span: Any) -> None:
    """Mark a session span OK and end it."""
    try:
        session_span.set_status(Status(StatusCode.OK))
    except Exception:
        pass
    session_span.end()
