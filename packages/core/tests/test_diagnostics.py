"""Tests for SDK diagnostics buffer / circuit breaker."""

from __future__ import annotations

import os

import pytest

from parlot.core import diagnostics as diag


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PARLOT_DIAGNOSTICS", "on")
    with diag._lock:
        diag._buffer.clear()
        diag._consecutive_failures = 0
        diag._circuit_open_until = 0.0
        diag._endpoint = ""
        diag._api_key = ""
    yield
    with diag._lock:
        diag._buffer.clear()


def test_diagnostics_enabled_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PARLOT_DIAGNOSTICS", raising=False)
    assert diag.diagnostics_enabled() is True


def test_diagnostics_opt_out(monkeypatch: pytest.MonkeyPatch):
    for value in ("off", "0", "false", "no", "OFF"):
        monkeypatch.setenv("PARLOT_DIAGNOSTICS", value)
        assert diag.diagnostics_enabled() is False


def test_record_and_drain():
    diag.record_diagnostic("export.trace", "boom", attributes={"x": 1})
    events = diag.drain_diagnostics()
    assert len(events) == 1
    assert events[0].kind == "export.trace"
    assert events[0].message == "boom"
    assert events[0].attributes["x"] == 1
    assert diag.drain_diagnostics() == []


def test_record_noop_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PARLOT_DIAGNOSTICS", "off")
    diag.record_diagnostic("export.trace", "boom")
    assert diag.drain_diagnostics() == []


def test_buffer_bounded():
    for i in range(100):
        diag.record_diagnostic("export.trace", f"n={i}")
    events = diag.drain_diagnostics()
    assert len(events) == diag._MAX_BUFFER
