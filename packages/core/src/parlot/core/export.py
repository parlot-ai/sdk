"""Shared OTLP export helpers for instrumentation packages."""

from __future__ import annotations

import logging
from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from parlot.core.attrs import is_exportable_span_name
from parlot.core.ingest_gate import is_parlot_ingest_disabled
from parlot.core.otlp_quota import attach_otlp_http_quota_capture, log_parlot_ingest_quota_once

logger = logging.getLogger("parlot.core.export")


def _short_error(exc: BaseException) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if len(msg) > 240:
        return msg[:237] + "..."
    return msg


class ExportFilterSpanExporter(SpanExporter):
    """Pass through only Conversation Contract + GenAI + voice spans."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        filtered = [span for span in spans if is_exportable_span_name(span.name)]
        if not filtered:
            return SpanExportResult.SUCCESS
        return self._exporter.export(filtered)

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)


class QuietOTLPSpanExporter(SpanExporter):
    """Wraps an OTLP span exporter; quota 429s are swallowed after one process log."""

    def __init__(
        self,
        exporter: SpanExporter,
        *,
        endpoint_label: str,
    ) -> None:
        self._exporter = exporter
        self._endpoint_label = endpoint_label
        self._quota_responses: list[tuple[int, str]] = []
        attach_otlp_http_quota_capture(
            exporter,
            on_quota=self._record_quota_response,
        )

    def _record_quota_response(self, status_code: int, body_text: str) -> None:
        self._quota_responses.append((status_code, body_text))

    def _swallow_quota_if_present(self) -> SpanExportResult | None:
        if not self._quota_responses:
            return None
        status_code, body_text = self._quota_responses[-1]
        if status_code == 429:
            log_parlot_ingest_quota_once(
                channel="trace",
                status_code=status_code,
                body_text=body_text,
            )
            return SpanExportResult.SUCCESS
        return None

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if is_parlot_ingest_disabled():
            return SpanExportResult.SUCCESS
        self._quota_responses.clear()
        try:
            result = self._exporter.export(spans)
        except Exception as exc:
            swallowed = self._swallow_quota_if_present()
            if swallowed is not None:
                return swallowed
            logger.warning(
                "Parlot trace export failed (%s): %s",
                self._endpoint_label,
                _short_error(exc),
            )
            return SpanExportResult.FAILURE

        swallowed = self._swallow_quota_if_present()
        if swallowed is not None:
            return swallowed
        if result == SpanExportResult.FAILURE:
            logger.warning(
                "Parlot trace export returned FAILURE (%s)",
                self._endpoint_label,
            )
        return result

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)
