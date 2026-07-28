"""
ParlotBaseProcessor — base SpanProcessor with shared span-mutation helpers.

All framework-specific instrumentation packages subclass this. The helpers
use the internal ReadableSpan API (_attributes, _events) because OTel's
public API does not allow post-creation attribute writes on ended spans.
"""

from __future__ import annotations

import logging
import time

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

from .logging import log_span_event
from .session import SessionState

logger = logging.getLogger("parlot.processor")
logger.setLevel(logging.DEBUG)


class ParlotBaseProcessor(SpanProcessor):
    """
    Subclass and override ``on_end`` (or the ``_enrich`` dispatch method) to
    add framework-specific span enrichment. Call ``super().on_start()`` /
    ``super().on_end()`` so shared debug logging runs.

    Do NOT wrap a downstream processor — add alongside BatchSpanProcessor:

        provider.add_span_processor(MyFrameworkProcessor())
        provider.add_span_processor(BatchSpanProcessor(your_exporter))
    """

    def on_start(self, span, parent_context=None) -> None:
        log_span_event("on_start", span)

    def on_end(self, span: ReadableSpan) -> None:
        log_span_event("on_end", span)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

    # ------------------------------------------------------------------
    # Shared helpers — used by all subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def _set(span: ReadableSpan, key: str, value) -> None:
        """Write an attribute into a ReadableSpan after it has ended."""
        if span._attributes is None:
            span._attributes = {}
        span._attributes[key] = value

    @staticmethod
    def _add_event(span: ReadableSpan, name: str, attributes: dict) -> None:
        """Append a span event to a ReadableSpan after it has ended."""
        from opentelemetry.sdk.trace import Event
        evt = Event(name=name, attributes=attributes, timestamp=time.time_ns())
        if hasattr(span, "_events") and isinstance(span._events, list):
            span._events.append(evt)

    @staticmethod
    def _trace_id_hex(span: ReadableSpan) -> str:
        return format(span.context.trace_id, "032x")

    @staticmethod
    def _maybe_update(state: SessionState, attr: str, value) -> None:
        """Set a state attribute only if it is currently falsy."""
        if value and not getattr(state, attr, ""):
            setattr(state, attr, str(value))


def assert_sync_span_processors(provider) -> bool:
    """Require ``SynchronousMultiSpanProcessor`` on the provider.

    Parlot processors rely on synchronous ``on_start`` / ``on_end`` ordering and
    often on ``contextvars`` copied at task creation. ``ConcurrentMultiSpanProcessor``
    runs handlers on worker threads and breaks that model.

    Returns ``False`` when ``ConcurrentMultiSpanProcessor`` is active (callers
    should disable OTel ``context.attach`` and similar). Raises ``RuntimeError``
    for unknown processor layouts.

    Uses OTel SDK-private ``_active_span_processor`` — re-validate on SDK upgrades.
    """
    from opentelemetry.sdk.trace import (
        ConcurrentMultiSpanProcessor,
        SynchronousMultiSpanProcessor,
    )

    asp = getattr(provider, "_active_span_processor", None)
    if asp is None:
        raise RuntimeError(
            "parlot: TracerProvider has no _active_span_processor; "
            "cannot verify synchronous span processing"
        )
    if isinstance(asp, ConcurrentMultiSpanProcessor):
        logger.error(
            "parlot: ConcurrentMultiSpanProcessor detected — "
            "unsupported for Parlot span processors (use synchronous layout)"
        )
        return False
    if not isinstance(asp, SynchronousMultiSpanProcessor):
        raise RuntimeError(
            f"parlot: unsupported active span processor {type(asp).__name__!r}; "
            "expected SynchronousMultiSpanProcessor"
        )
    return True
