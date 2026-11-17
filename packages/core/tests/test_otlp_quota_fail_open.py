"""OTLP export must not block the host agent on Parlot ingest quota (HTTP 429)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult

from parlot.core.export import QuietOTLPSpanExporter
from parlot.core.otlp_quota import reset_parlot_quota_log_for_tests


def test_otlp_quota_429_does_not_raise_and_host_call_continues(caplog: pytest.LogCaptureFixture) -> None:
    reset_parlot_quota_log_for_tests()
    caplog.set_level("WARNING", logger="parlot.core.otlp_quota")

    body = (
        '{"error":"quota_exceeded","resets_at":"2026-08-15T00:00:00.000Z",'
        '"upgrade_url":"https://app.parlot.ai/settings/billing"}'
    )
    inner = MagicMock()

    quiet = QuietOTLPSpanExporter(
        inner,
        endpoint_label="https://ingest.example/v1/traces",
    )

    def export_with_quota(_spans: object) -> SpanExportResult:
        quiet._record_quota_response(429, body)
        return SpanExportResult.FAILURE

    inner.export.side_effect = export_with_quota

    def host_voice_turn() -> str:
        return "agent_response_ok"

    result = quiet.export([])
    host_outcome = host_voice_turn()

    assert result is SpanExportResult.SUCCESS
    assert host_outcome == "agent_response_ok"
    assert any(
        "quota exceeded" in r.message
        and "resets_at=2026-08-15" in r.message
        and "upgrade_url=https://app.parlot.ai/settings/billing" in r.message
        for r in caplog.records
    )
