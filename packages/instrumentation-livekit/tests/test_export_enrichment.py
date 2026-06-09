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
from parlot.instrumentation.livekit._processor import (
    LiveKitGenAIProcessor,
    _LiveKitSessionState,
)

_COMPARE_SESSION_DIR = (
    Path(__file__).resolve().parents[4]
    / "calcom-receptionist"
    / "lk-agent"
    / "compare"
    / "019eae627c627194aaa9232ab1fbc746"
)

_COMPARE_SESSION_019EAE86 = (
    Path(__file__).resolve().parents[4]
    / "calcom-receptionist"
    / "lk-agent"
    / "compare"
    / "019eae86d1847079a0e34f57aa48f01b"
)


class _FakeMetrics:
    def record_usage_collected(self, state, metrics_obj) -> None:
        pass


class _FakeTraceContext:
    trace_id = 0
    span_id = 0


def _replay_state(session_id: str) -> _LiveKitSessionState:
    return _LiveKitSessionState(parlot_session_id=session_id)


def _patch_bootstrap(mp: pytest.MonkeyPatch, bootstrap: SimpleNamespace) -> None:
    mp.setattr(
        "parlot.instrumentation.livekit._session.get_job_bootstrap",
        lambda: bootstrap,
    )
    mp.setattr(
        "parlot.instrumentation.livekit._processor.get_job_bootstrap",
        lambda: bootstrap,
    )


class _ReplaySpan:
    """Minimal ReadableSpan stand-in (MagicMock breaks attribute mutation)."""

    def __init__(self, name: str, *, attrs: dict | None = None, end_ns: int = 2_000_000_000) -> None:
        self.name = name
        self._attributes = dict(attrs or {})
        self._events: list = []
        self.context = _FakeTraceContext()
        self.start_time = end_ns - 1_000_000_000
        self.end_time = end_ns
        self.status = None

    @property
    def attributes(self):
        return self._attributes


def test_export_enrichment_applies_tokens_after_on_end() -> None:
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = _replay_state("sess-1")
    bootstrap = SimpleNamespace(state=state)

    downstream = MagicMock()
    downstream.export.return_value = 0

    exporter = EnrichingExportSpanExporter(downstream, processor)

    span = _ReplaySpan("llm_node")
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
        _patch_bootstrap(mp, bootstrap)
        handle_plugin_metrics_collected(processor, llm)

    with pytest.MonkeyPatch.context() as mp:
        _patch_bootstrap(mp, bootstrap)
        exporter.export([span])

    assert span._attributes.get(ATTR_GEN_AI_IN_TOKENS) == 42
    assert span._attributes.get(ATTR_GEN_AI_OUT_TOKENS) == 7
    downstream.export.assert_called_once()


def _span_from_compare_row(row: dict, *, end_ns: int) -> _ReplaySpan:
    attrs = dict(row.get("data", {}).get("attributes") or {})
    attrs.pop(ATTR_GEN_AI_IN_TOKENS, None)
    attrs.pop(ATTR_GEN_AI_OUT_TOKENS, None)
    return _ReplaySpan(row["category"], attrs=attrs, end_ns=end_ns)


@pytest.mark.skipif(
    not _COMPARE_SESSION_DIR.is_dir(),
    reason="compare session fixture not present",
)
def test_compare_session_export_enrichment_tokens() -> None:
    """Replay compare session plugins after llm_node on_end; export must attach tokens."""
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = _replay_state("019eae627c627194aaa9232ab1fbc746")
    bootstrap = SimpleNamespace(state=state)

    llm_spans: list[_ReplaySpan] = []
    for line in (_COMPARE_SESSION_DIR / "spans.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("category") != "llm_node":
            continue
        end_ns = int(float(row["ts"]) * 1_000_000_000)
        span = _span_from_compare_row(row, end_ns=end_ns)
        with pytest.MonkeyPatch.context() as mp:
            _patch_bootstrap(mp, bootstrap)
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
            _patch_bootstrap(mp, bootstrap)
            handle_plugin_metrics_collected(processor, llm)

    with pytest.MonkeyPatch.context() as mp:
        _patch_bootstrap(mp, bootstrap)
        processor.enrich_spans_for_export(llm_spans)

    tokens_in = sum(int(s._attributes.get(ATTR_GEN_AI_IN_TOKENS) or 0) for s in llm_spans)
    tokens_out = sum(int(s._attributes.get(ATTR_GEN_AI_OUT_TOKENS) or 0) for s in llm_spans)
    enriched = sum(
        1 for s in llm_spans if s._attributes.get(ATTR_GEN_AI_IN_TOKENS) is not None
    )
    assert enriched > 0
    assert tokens_in > 0
    assert tokens_out > 0


def test_agent_turn_does_not_consume_plugin_tokens() -> None:
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = _replay_state("sess-1")
    bootstrap = SimpleNamespace(state=state)

    llm = SimpleNamespace(
        type="llm_metrics",
        speech_id="",
        prompt_tokens=100,
        completion_tokens=10,
        metadata=None,
    )
    with pytest.MonkeyPatch.context() as mp:
        _patch_bootstrap(mp, bootstrap)
        handle_plugin_metrics_collected(processor, llm)

    llm_span = _ReplaySpan("llm_node")
    agent_span = _ReplaySpan("agent_turn")

    with pytest.MonkeyPatch.context() as mp:
        _patch_bootstrap(mp, bootstrap)
        processor.on_end(llm_span)
        processor.on_end(agent_span)

    assert llm_span._attributes.get(ATTR_GEN_AI_IN_TOKENS) == 100
    assert agent_span._attributes.get(ATTR_GEN_AI_IN_TOKENS) is None


@pytest.mark.skipif(
    not _COMPARE_SESSION_019EAE86.is_dir(),
    reason="compare session fixture not present",
)
def test_compare_session_token_totals_match_plugins() -> None:
    """Replay 019eae86: span token sum should match plugin llm_metrics totals."""
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = _replay_state("019eae86d1847079a0e34f57aa48f01b")
    bootstrap = SimpleNamespace(state=state)

    plugin_in = 0
    plugin_out = 0
    for line in (_COMPARE_SESSION_019EAE86 / "plugins.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        data = row.get("data") or {}
        if data.get("type") != "llm_metrics":
            continue
        plugin_in += int(data.get("prompt_tokens") or 0)
        plugin_out += int(data.get("completion_tokens") or 0)
        llm = SimpleNamespace(
            type="llm_metrics",
            speech_id=data.get("speech_id", ""),
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
            metadata=data.get("metadata"),
        )
        with pytest.MonkeyPatch.context() as mp:
            _patch_bootstrap(mp, bootstrap)
            handle_plugin_metrics_collected(processor, llm)

    llm_spans: list[_ReplaySpan] = []
    agent_spans: list[_ReplaySpan] = []
    for line in (_COMPARE_SESSION_019EAE86 / "spans.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cat = row.get("category")
        if cat not in ("llm_node", "agent_turn"):
            continue
        end_ns = int(float(row["ts"]) * 1_000_000_000)
        span = _span_from_compare_row(row, end_ns=end_ns)
        with pytest.MonkeyPatch.context() as mp:
            _patch_bootstrap(mp, bootstrap)
            processor.on_end(span)
        if cat == "llm_node":
            llm_spans.append(span)
        else:
            agent_spans.append(span)

    span_in = sum(int(s._attributes.get(ATTR_GEN_AI_IN_TOKENS) or 0) for s in llm_spans)
    span_out = sum(
        int(s._attributes.get(ATTR_GEN_AI_OUT_TOKENS) or 0) for s in llm_spans
    )
    agent_in = sum(
        int(s._attributes.get(ATTR_GEN_AI_IN_TOKENS) or 0) for s in agent_spans
    )

    assert plugin_in > 0
    assert span_in == plugin_in
    assert span_out == plugin_out
    assert agent_in == 0
