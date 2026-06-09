"""Tests for dev-only telemetry compare JSONL logging."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from parlot.instrumentation.livekit._telemetry_compare import (
    TelemetryCompareLogger,
    compare_enabled,
    compare_plugins_enabled,
    get_compare_logger,
)


@pytest.fixture(autouse=True)
def _clear_compare_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PARLOT_TELEMETRY_COMPARE", raising=False)
    monkeypatch.delenv("PARLOT_TELEMETRY_COMPARE_PLUGINS", raising=False)
    monkeypatch.delenv("PARLOT_TELEMETRY_COMPARE_DIR", raising=False)


def test_compare_disabled_by_default() -> None:
    assert compare_enabled() is False
    assert compare_plugins_enabled() is False
    logger = TelemetryCompareLogger()
    logger.log_event("sess-x", category="close", data={"reason": "test"})
    assert "sess-x" not in logger._sessions


def test_compare_writes_events_and_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARLOT_TELEMETRY_COMPARE", "1")
    monkeypatch.setenv("PARLOT_TELEMETRY_COMPARE_DIR", str(tmp_path))

    logger = TelemetryCompareLogger()
    logger.log_event(
        "sess-compare-1",
        category="conversation_item_added",
        data={"role": "assistant", "metrics": {"llm_ttft": 0.2}},
        turn_index=1,
    )
    logger.log_span(
        "sess-compare-1",
        span_name="agent_turn",
        attrs={"gen_ai.usage.input_tokens": 10},
    )
    logger.finalize_session("sess-compare-1")

    session_dir = tmp_path / "sess-compare-1"
    events_lines = (session_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    spans_lines = (session_dir / "spans.jsonl").read_text(encoding="utf-8").strip().splitlines()
    summary = json.loads((session_dir / "summary.json").read_text(encoding="utf-8"))

    assert len(events_lines) == 1
    assert len(spans_lines) == 1
    event_row = json.loads(events_lines[0])
    assert event_row["path"] == "events"
    assert event_row["category"] == "conversation_item_added"
    span_row = json.loads(spans_lines[0])
    assert span_row["path"] == "spans"
    assert span_row["category"] == "agent_turn"
    assert summary["event_turns"] == 1
    assert summary["span_turns"] == 1


def test_compare_plugins_jsonl_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARLOT_TELEMETRY_COMPARE", "1")
    monkeypatch.setenv("PARLOT_TELEMETRY_COMPARE_PLUGINS", "1")
    monkeypatch.setenv("PARLOT_TELEMETRY_COMPARE_DIR", str(tmp_path))

    logger = get_compare_logger()
    logger.log_plugin_metrics(
        "sess-plugins",
        metrics_obj=SimpleNamespace(
            type="llm_metrics",
            speech_id="sp-1",
            ttft=0.3,
            prompt_tokens=50,
            completion_tokens=20,
            metadata=SimpleNamespace(model_name="gpt-4o", model_provider="openai"),
        ),
    )
    logger.finalize_session("sess-plugins")

    plugins_path = tmp_path / "sess-plugins" / "plugins.jsonl"
    row = json.loads(plugins_path.read_text(encoding="utf-8").strip())
    assert row["path"] == "plugins"
    assert row["data"]["type"] == "llm_metrics"
    assert row["data"]["speech_id"] == "sp-1"
