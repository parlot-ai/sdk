"""Export-time deferred LLM token enrichment."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from parlot.core.attrs import ATTR_GEN_AI_IN_TOKENS, ATTR_GEN_AI_OUT_TOKENS
from parlot.instrumentation.livekit._export_filter import EnrichingExportSpanExporter
from parlot.instrumentation.livekit._plugin_metrics import handle_plugin_metrics_collected
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor

_COMPARE_SESSION_DIR = (
    Path(__file__).resolve().parents[4]
    / "calcom-receptionist"
    / "lk-agent"
    / "compare"
    / "019eae627c627194aaa9232ab1fbc746"
)


class _FakeMetrics:
    def record_usage_collected(self, state, metrics_obj) -> None:
        pass


def test_export_enrichment_applies_tokens_after_on_end() -> None:
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = SimpleNamespace(parlot_session_id="sess-1", active_speech_id="")
    bootstrap = SimpleNamespace(state=state)

    downstream = MagicMock()
    downstream.export.return_value = 0

    exporter = EnrichingExportSpanExporter(downstream, processor)

    span = MagicMock()
    span.name = "llm_node"
    span._attributes = {}
    span._events = []
    span.attributes = span._attributes
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    processor.on_end(span)

    assert span._attributes.get(ATTR_GEN_AI_IN_TOKENS) is None

    llm = SimpleNamespace(
        type="llm_metrics",
        speech_id="sp-1",
        prompt_tokens=42,
        completion_tokens=7,
        metadata=None,
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "parlot.instrumentation.livekit._session.get_job_bootstrap",
            lambda: bootstrap,
        )
        handle_plugin_metrics_collected(processor, llm)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "parlot.instrumentation.livekit._session.get_job_bootstrap",
            lambda: bootstrap,
        )
        exporter.export([span])

    assert span._attributes.get(ATTR_GEN_AI_IN_TOKENS) == 42
    assert span._attributes.get(ATTR_GEN_AI_OUT_TOKENS) == 7
    downstream.export.assert_called_once()


def _span_from_compare_row(row: dict, *, end_ns: int) -> MagicMock:
    span = MagicMock()
    span.name = row["category"]
    span._attributes = dict(row.get("data", {}).get("attributes") or {})
    span._events = []
    span.attributes = span._attributes
    span.start_time = end_ns - 1_000_000_000
    span.end_time = end_ns
    return span


@pytest.mark.skipif(
    not _COMPARE_SESSION_DIR.is_dir(),
    reason="compare session fixture not present",
)
def test_compare_session_export_enrichment_tokens() -> None:
    """Replay compare session plugins after llm_node on_end; export must attach tokens."""
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = SimpleNamespace(
        parlot_session_id="019eae627c627194aaa9232ab1fbc746",
        active_speech_id="",
    )
    bootstrap = SimpleNamespace(state=state)

    llm_spans: list[MagicMock] = []
    for line in (_COMPARE_SESSION_DIR / "spans.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("category") != "llm_node":
            continue
        end_ns = int(float(row["ts"]) * 1_000_000_000)
        span = _span_from_compare_row(row, end_ns=end_ns)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "parlot.instrumentation.livekit._session.get_job_bootstrap",
                lambda: bootstrap,
            )
            processor.on_end(span)
        llm_spans.append(span)

    assert len(llm_spans) >= 1
    for span in llm_spans:
        assert span._attributes.get(ATTR_GEN_AI_IN_TOKENS) is None

    for line in (_COMPARE_SESSION_DIR / "plugins.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        data = row.get("data") or {}
        if data.get("type") != "llm_metrics":
            continue
        llm = SimpleNamespace(
            type="llm_metrics",
            speech_id=data.get("speech_id", ""),
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            metadata=data.get("metadata"),
        )
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "parlot.instrumentation.livekit._session.get_job_bootstrap",
                lambda: bootstrap,
            )
            handle_plugin_metrics_collected(processor, llm)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "parlot.instrumentation.livekit._session.get_job_bootstrap",
            lambda: bootstrap,
        )
        processor.enrich_spans_for_export(llm_spans)

    tokens_in = sum(int(s._attributes.get(ATTR_GEN_AI_IN_TOKENS) or 0) for s in llm_spans)
    tokens_out = sum(int(s._attributes.get(ATTR_GEN_AI_OUT_TOKENS) or 0) for s in llm_spans)
    enriched = sum(
        1 for s in llm_spans if s._attributes.get(ATTR_GEN_AI_IN_TOKENS) is not None
    )
    assert enriched > 0
    assert tokens_in > 0
    assert tokens_out > 0
