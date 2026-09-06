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
    assert "parlot: telemetry bootstrap request failed — failed to connect to host" in error_records[0].message
    assert error_records[0].exc_info is None
