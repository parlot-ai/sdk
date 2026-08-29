"""OTLP exporters that log export failures without noisy stack traces."""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, MetricsData
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from parlot.core.diagnostics import DiagnosticsCollector

logger = logging.getLogger("parlot.instrumentation.livekit.export")


def _short_error(exc: BaseException) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if len(msg) > 240:
        return msg[:237] + "..."
    return msg


class QuietOTLPSpanExporter(SpanExporter):
    """Wraps an OTLP span exporter with one-line warning logs on failure."""

    def __init__(
        self,
        exporter: SpanExporter,
        *,
        endpoint_label: str,
        diagnostics: Optional[DiagnosticsCollector] = None,
    ) -> None:
        self._exporter = exporter
        self._endpoint_label = endpoint_label
        self._diagnostics = diagnostics

    def _record(
        self, kind: str, message: str, *, exc: BaseException | None = None
    ) -> None:
        if self._diagnostics is None:
            return
        try:
            self._diagnostics.record(kind, message, exc=exc)
        except Exception:
            return

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self._exporter.export(spans)
            if result == SpanExportResult.FAILURE:
                msg = f"Parlot trace export returned FAILURE ({self._endpoint_label})"
                logger.warning("%s", msg)
                self._record("export.trace", msg)
            return result
        except Exception as exc:
            logger.warning(
                "Parlot trace export failed (%s): %s",
                self._endpoint_label,
                _short_error(exc),
            )
            self._record("export.trace", _short_error(exc), exc=exc)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)


class QuietOTLPMetricExporter(MetricExporter):
    """Wraps an OTLP metric exporter with one-line warning logs on failure."""

    def __init__(
        self,
        exporter: MetricExporter,
        *,
        endpoint_label: str,
        diagnostics: Optional[DiagnosticsCollector] = None,
    ) -> None:
        super().__init__(
            preferred_temporality=exporter._preferred_temporality,
            preferred_aggregation=exporter._preferred_aggregation,
        )
        self._exporter = exporter
        self._endpoint_label = endpoint_label
        self._diagnostics = diagnostics

    def _record(
        self, kind: str, message: str, *, exc: BaseException | None = None
    ) -> None:
        if self._diagnostics is None:
            return
        try:
            self._diagnostics.record(kind, message, exc=exc)
        except Exception:
            return

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs,
    ) -> MetricExportResult:
        try:
            result = self._exporter.export(
                metrics_data, timeout_millis=timeout_millis, **kwargs
            )
            if result == MetricExportResult.FAILURE:
                msg = f"Parlot metrics export returned FAILURE ({self._endpoint_label})"
                logger.warning("%s", msg)
                self._record("export.metrics", msg)
            return result
        except Exception as exc:
            logger.warning(
                "Parlot metrics export failed (%s): %s",
                self._endpoint_label,
                _short_error(exc),
            )
            self._record("export.metrics", _short_error(exc), exc=exc)
            return MetricExportResult.FAILURE

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        self._exporter.shutdown(timeout_millis=timeout_millis, **kwargs)

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self._exporter.force_flush(timeout_millis=timeout_millis)
