"""Tests for SDK diagnostics buffer / circuit breaker."""

from __future__ import annotations

import pytest

from parlot.core.context import ParlotContext
from parlot.core import diagnostics as diag


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch) -> ParlotContext:
    monkeypatch.setenv("PARLOT_DIAGNOSTICS", "on")
    return ParlotContext()


def test_diagnostics_enabled_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PARLOT_DIAGNOSTICS", raising=False)
    assert diag.diagnostics_enabled() is True


def test_diagnostics_opt_out(monkeypatch: pytest.MonkeyPatch):
    for value in ("off", "0", "false", "no", "OFF"):
        monkeypatch.setenv("PARLOT_DIAGNOSTICS", value)
        assert diag.diagnostics_enabled() is False


def test_record_and_drain(ctx: ParlotContext):
    ctx.diagnostics.record("export.trace", "boom", attributes={"x": 1})
    events = ctx.diagnostics.drain()
    assert len(events) == 1
    assert events[0].kind == "export.trace"
    assert events[0].message == "boom"
    assert events[0].attributes["x"] == 1
    assert ctx.diagnostics.drain() == []


def test_record_noop_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PARLOT_DIAGNOSTICS", "off")
    ctx = ParlotContext()
    ctx.diagnostics.record("export.trace", "boom")
    assert ctx.diagnostics.drain() == []


def test_buffer_bounded(ctx: ParlotContext):
    for i in range(100):
        ctx.diagnostics.record("export.trace", f"n={i}")
    events = ctx.diagnostics.drain()
    assert len(events) == diag._MAX_BUFFER


def test_two_contexts_isolate_diagnostics(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PARLOT_DIAGNOSTICS", "on")
    a = ParlotContext()
    b = ParlotContext()
    a.diagnostics.record("export.trace", "from-a")
    b.diagnostics.record("export.metrics", "from-b")
    assert [e.message for e in a.diagnostics.drain()] == ["from-a"]
    assert [e.message for e in b.diagnostics.drain()] == ["from-b"]
