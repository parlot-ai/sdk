"""Drop non-contract spans before OTLP export."""

from __future__ import annotations

from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from parlot.core.attrs import SPAN_PARLOT_SESSION_CLOSE

SPAN_CONVERSATION_SESSION = "conversation.session"
SPAN_PARLOT_TURN = "parlot.turn"

_EXPORTABLE_OPERATIONAL_SPANS = frozenset({
    "user_turn",
    "agent_turn",
    "llm_node",
    "llm_request",
    "llm_request_run",
    "tts_node",
    "tts_request_run",
    "function_tool",
    "amd",
    "eou_detection",
})

EXPORTABLE_SPAN_NAMES = frozenset({
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_TURN,
    SPAN_PARLOT_SESSION_CLOSE,
    "lk.agent_handoff",
    *_EXPORTABLE_OPERATIONAL_SPANS,
})


class ExportFilterSpanExporter(SpanExporter):
    """Pass through only spans required by the Conversation Contract."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        filtered = [span for span in spans if span.name in EXPORTABLE_SPAN_NAMES]
        if not filtered:
            return SpanExportResult.SUCCESS
        return self._exporter.export(filtered)

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)
