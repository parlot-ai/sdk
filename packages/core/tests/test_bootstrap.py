"""Tests for parlot.core.bootstrap error logging."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from parlot.core.bootstrap import fetch_telemetry_bootstrap
from parlot.core.context import ParlotContext


def test_fetch_telemetry_bootstrap_error_logs_without_traceback(caplog):
    context = ParlotContext()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.side_effect = ConnectionError("failed to connect to host")
        mock_client_cls.return_value = mock_client

        with caplog.at_level("DEBUG"):
            result = fetch_telemetry_bootstrap(
                "https://api.parlot.ai", "key-123", context
            )

    assert result is None
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    assert (
        "parlot: telemetry bootstrap request failed — failed to connect to host"
        in error_records[0].message
    )
    assert "endpoint=https://api.parlot.ai" in error_records[0].message
    assert error_records[0].exc_info is None


def test_fetch_telemetry_bootstrap_success_logs_info(caplog):
    context = ParlotContext()
    payload = {"recording": {"enabled": False}}

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        with (
            patch(
                "parlot.core.runtime.runtime_from_bootstrap",
                return_value=MagicMock(),
            ),
            caplog.at_level("INFO"),
        ):
            result = fetch_telemetry_bootstrap(
                "http://localhost:8788/", "key-123", context
            )

    assert result is payload
    info_records = [r for r in caplog.records if r.levelname == "INFO"]
    assert any(
        "parlot: telemetry bootstrap ok (endpoint=http://localhost:8788)" in r.message
        for r in info_records
    )


def test_fetch_telemetry_bootstrap_http_error_includes_endpoint(caplog):
    context = ParlotContext()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        with caplog.at_level("ERROR"):
            result = fetch_telemetry_bootstrap(
                "http://localhost:8788", "bad-key", context
            )

    assert result is None
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    assert "status=401" in error_records[0].message
    assert "endpoint=http://localhost:8788" in error_records[0].message
