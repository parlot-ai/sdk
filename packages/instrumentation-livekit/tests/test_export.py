"""Tests for quiet OTLP export wrappers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.metrics.export import MetricExportResult
from opentelemetry.sdk.trace.export import SpanExportResult

from parlot.instrumentation.livekit._export import QuietOTLPMetricExporter, QuietOTLPSpanExporter


def test_quiet_span_exporter_logs_failure_not_raises():
    inner = MagicMock()
    inner.export.side_effect = RuntimeError("503 Service Unavailable")
    wrapper = QuietOTLPSpanExporter(inner, endpoint_label="http://localhost:4318/v1/traces")

    result = wrapper.export([])

    assert result is SpanExportResult.FAILURE
    inner.export.assert_called_once()


def test_quiet_metric_exporter_logs_failure_not_raises():
    inner = MagicMock()
    inner.export.side_effect = RuntimeError("connection refused")
    inner._preferred_temporality = {}
    inner._preferred_aggregation = {}
    wrapper = QuietOTLPMetricExporter(inner, endpoint_label="http://localhost:4318/v1/metrics")

    result = wrapper.export(MagicMock())

    assert result is MetricExportResult.FAILURE
    inner.export.assert_called_once()
