"""Remap LiveKit child spans onto per-turn trace_ids at OTLP export time."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import SpanContext, TraceFlags
from opentelemetry.util.types import Attributes

from parlot.core.attrs import ATTR_SESSION_ID, ATTR_TURN_INDEX

if TYPE_CHECKING:
    from ._processor import LiveKitGenAIProcessor

_SKIP_SPAN_NAMES = frozenset(
    {"job_entrypoint", "conversation.session", "parlot.turn", "parlot.session.close"}
)


def _attr_int(attrs: Attributes, key: str) -> int | None:
    if not attrs:
        return None
    val = attrs.get(key)
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return None


def _parse_trace_id(hex_id: str) -> int:
    return int(hex_id, 16)


class _RemappedReadableSpan:
    """ReadableSpan view with an overridden trace (and optional parent) context."""

    def __init__(
        self,
        inner: ReadableSpan,
        context: SpanContext,
        *,
        parent: SpanContext | None = None,
    ) -> None:
        self._inner = inner
        self._context = context
        self._parent = parent

    @property
    def context(self) -> SpanContext:
        return self._context

    def get_span_context(self) -> SpanContext:
        return self._context

    @property
    def parent(self) -> SpanContext | None:
        if self._parent is not None:
            return self._parent
        return self._inner.parent

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class TurnTraceRemappingExporter(SpanExporter):
    """
    Rewrites OTLP-bound spans so operational children share each turn's trace_id.

    Lookup uses the processor registry populated when ``parlot.turn`` roots emit.
    """

    def __init__(
        self,
        delegate: SpanExporter,
        processor: "LiveKitGenAIProcessor",
    ) -> None:
        self._delegate = delegate
        self._processor = processor

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        remapped: list[ReadableSpan] = []
        for span in spans:
            wrapper = self._maybe_remap(span)
            if wrapper is not None:
                remapped.append(cast(ReadableSpan, wrapper))
            else:
                remapped.append(span)
        return self._delegate.export(remapped)

    def shutdown(self) -> None:
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)

    def _maybe_remap(self, span: ReadableSpan) -> _RemappedReadableSpan | None:
        if span.name in _SKIP_SPAN_NAMES:
            return None

        attrs = span.attributes
        session_id = attrs.get(ATTR_SESSION_ID) if attrs else None
        if not session_id or not isinstance(session_id, str):
            return None

        turn_index = _attr_int(attrs, ATTR_TURN_INDEX)
        if turn_index is None:
            return None

        entry = self._processor.lookup_turn_trace(session_id, turn_index)
        if entry is None:
            return None

        turn_trace_hex, turn_root_span_hex = entry
        turn_trace_id = _parse_trace_id(turn_trace_hex)
        turn_root_span_id = int(turn_root_span_hex, 16)

        inner_ctx = span.get_span_context()
        if inner_ctx is None or not inner_ctx.is_valid:
            return None
        if inner_ctx.trace_id == turn_trace_id:
            return None

        new_ctx = SpanContext(
            trace_id=turn_trace_id,
            span_id=inner_ctx.span_id,
            is_remote=inner_ctx.is_remote,
            trace_flags=inner_ctx.trace_flags,
        )

        parent_ctx: SpanContext | None = None
        parent = span.parent
        if parent is None or parent.trace_id != turn_trace_id:
            parent_ctx = SpanContext(
                trace_id=turn_trace_id,
                span_id=turn_root_span_id,
                is_remote=False,
                trace_flags=TraceFlags(0x01),
            )

        return _RemappedReadableSpan(span, new_ctx, parent=parent_ctx)
