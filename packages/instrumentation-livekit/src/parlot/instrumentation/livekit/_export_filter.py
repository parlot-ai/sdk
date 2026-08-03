"""LiveKit-only export wrappers (shared allowlist lives in ``parlot.core.export``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

if TYPE_CHECKING:
    from ._processor import LiveKitGenAIProcessor


class EnrichingExportSpanExporter(SpanExporter):
    """Apply deferred plugin token enrichment before downstream export."""

    def __init__(
        self,
        exporter: SpanExporter,
        processor: "LiveKitGenAIProcessor",
    ) -> None:
        self._exporter = exporter
        self._processor = processor

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        batch = list(spans)
        self._processor.enrich_spans_for_export(batch)
        return self._exporter.export(batch)

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)
