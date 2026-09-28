"""Tests for base_parlotize misconfiguration logging."""

from __future__ import annotations

from unittest.mock import patch

from parlot.core.parlotize import base_parlotize


def test_base_parlotize_logs_error_when_endpoint_missing(caplog, monkeypatch):
    monkeypatch.delenv("PARLOT_ENDPOINT", raising=False)
    monkeypatch.delenv("PARLOT_API_KEY", raising=False)

    with (
        patch("parlot.core.bootstrap.fetch_telemetry_bootstrap") as mock_fetch,
        caplog.at_level("ERROR"),
    ):
        base_parlotize("test-agent", api_key="key-123")

    mock_fetch.assert_not_called()
    messages = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert any("parlot: PARLOT_ENDPOINT is not set" in m for m in messages)
    assert not any("PARLOT_API_KEY is not set" in m for m in messages)


def test_base_parlotize_logs_error_when_api_key_missing(caplog, monkeypatch):
    monkeypatch.delenv("PARLOT_API_KEY", raising=False)
    monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:8788")

    with (
        patch("parlot.core.bootstrap.fetch_telemetry_bootstrap") as mock_fetch,
        caplog.at_level("ERROR"),
    ):
        base_parlotize("test-agent")

    mock_fetch.assert_not_called()
    messages = [r.message for r in caplog.records if r.levelname == "ERROR"]
    assert any(
        "parlot: PARLOT_API_KEY is not set; telemetry will not authenticate" in m
        for m in messages
    )
    assert not any("PARLOT_ENDPOINT is not set" in m for m in messages)


def test_base_parlotize_fetches_bootstrap_when_configured(caplog, monkeypatch):
    monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:8788")
    monkeypatch.setenv("PARLOT_API_KEY", "key-123")

    with patch("parlot.core.bootstrap.fetch_telemetry_bootstrap") as mock_fetch:
        result = base_parlotize("test-agent")

    mock_fetch.assert_called_once()
    assert mock_fetch.call_args.args[0] == "http://localhost:8788"
    assert mock_fetch.call_args.args[1] == "key-123"
    assert result.endpoint == "http://localhost:8788"
    assert result.api_key == "key-123"
