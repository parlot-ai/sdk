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

from .session import SessionState

logger = logging.getLogger("parlot.processor")


class ParlotBaseProcessor(SpanProcessor):
    """
    Subclass and override ``on_end`` (or the ``_enrich`` dispatch method) to
    add framework-specific span enrichment.

    Do NOT wrap a downstream processor — add alongside BatchSpanProcessor:

        provider.add_span_processor(MyFrameworkProcessor())
        provider.add_span_processor(BatchSpanProcessor(your_exporter))
    """

    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        pass

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
