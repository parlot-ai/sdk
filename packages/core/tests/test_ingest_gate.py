"""Free-plan ingest gate: bootstrap deny + OTLP 429 latch without raising."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult

from parlot.core.export import QuietOTLPSpanExporter
from parlot.core.ingest_gate import (
    apply_bootstrap_ingest_policy,
    is_parlot_ingest_disabled,
    reset_parlot_ingest_gate_for_tests,
)
from parlot.core.otlp_quota import reset_parlot_quota_log_for_tests
from parlot.core.recording import should_record
from parlot.core.runtime import runtime_from_bootstrap


@pytest.fixture(autouse=True)
def _reset_gate() -> None:
    reset_parlot_ingest_gate_for_tests()
    reset_parlot_quota_log_for_tests()
    yield
    reset_parlot_ingest_gate_for_tests()
    reset_parlot_quota_log_for_tests()


def test_bootstrap_ingest_denied_latches_and_skips_export(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="parlot.core.ingest_gate")
    allowed = apply_bootstrap_ingest_policy(
        {
            "ingest": {
                "allowed": False,
                "error": "quota_exceeded",
                "resets_at": "2026-12-01T00:00:00.000Z",
                "upgrade_url": "https://app.parlot.ai/settings/billing",
            }
        }
    )
    assert allowed is False
    assert is_parlot_ingest_disabled() is True
    assert any("ingest disabled" in r.message for r in caplog.records)

    inner = MagicMock()
    quiet = QuietOTLPSpanExporter(inner, endpoint_label="https://ex/v1/traces")
    assert quiet.export([]) is SpanExportResult.SUCCESS
    inner.export.assert_not_called()

    assert should_record("agent-a", record_config=True) is False


def test_otlp_429_latches_subsequent_exports() -> None:
    body = (
        '{"error":"quota_exceeded","resets_at":"2026-08-15T00:00:00.000Z",'
        '"upgrade_url":"https://app.parlot.ai/settings/billing"}'
    )
    inner = MagicMock()
    quiet = QuietOTLPSpanExporter(inner, endpoint_label="https://ex/v1/traces")

    def export_with_quota(_spans: object) -> SpanExportResult:
        quiet._record_quota_response(429, body)
        return SpanExportResult.FAILURE

    inner.export.side_effect = export_with_quota
    assert quiet.export([]) is SpanExportResult.SUCCESS
    assert is_parlot_ingest_disabled() is True

    inner.export.side_effect = None
    assert quiet.export([]) is SpanExportResult.SUCCESS
    # Second export must not call the inner exporter once latched.
    assert inner.export.call_count == 1


def test_runtime_parses_ingest_denied() -> None:
    ctx = runtime_from_bootstrap(
        "https://ingest.example",
        "key",
        {
            "tenant_id": "org-1",
            "content_bucket": "b",
            "r2_endpoint": "https://r2.example",
            "ingest": {
                "allowed": False,
                "error": "quota_exceeded",
                "resets_at": "2026-12-01T00:00:00.000Z",
                "upgrade_url": "https://app.parlot.ai/settings/billing",
            },
        },
    )
    assert ctx.ingest_allowed is False
    assert ctx.ingest_error == "quota_exceeded"
    assert ctx.ingest_resets_at.startswith("2026-12-01")


def test_bootstrap_omitted_ingest_keeps_export_on() -> None:
    assert apply_bootstrap_ingest_policy({}) is True
    assert is_parlot_ingest_disabled() is False
    inner = MagicMock()
    inner.export = MagicMock(return_value=SpanExportResult.SUCCESS)
    quiet = QuietOTLPSpanExporter(inner, endpoint_label="https://ex/v1/traces")
    assert quiet.export([]) is SpanExportResult.SUCCESS
    inner.export.assert_called_once()
