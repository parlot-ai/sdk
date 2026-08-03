"""Export-time deferred LLM token enrichment."""

from __future__ import annotations

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


class _FakeMetrics:
    def record_usage_collected(self, state, metrics_obj) -> None:
        pass

    def record_turn(self, state, **kwargs) -> None:
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


def test_export_enrichment_token_totals_match_plugins() -> None:
    """Synthetic multi-span replay: llm_node token sum matches plugin llm_metrics."""
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = _replay_state("sess-tokens")
    bootstrap = SimpleNamespace(state=state)

    metrics = [
        SimpleNamespace(
            type="llm_metrics",
            speech_id="sp-a",
            prompt_tokens=10,
            completion_tokens=3,
            metadata=None,
        ),
        SimpleNamespace(
            type="llm_metrics",
            speech_id="sp-b",
            prompt_tokens=20,
            completion_tokens=5,
            metadata=None,
        ),
    ]
    for llm in metrics:
        with pytest.MonkeyPatch.context() as mp:
            _patch_bootstrap(mp, bootstrap)
            handle_plugin_metrics_collected(processor, llm)

    llm_spans = [_ReplaySpan("llm_node"), _ReplaySpan("llm_node")]
    agent_spans = [_ReplaySpan("agent_turn")]

    with pytest.MonkeyPatch.context() as mp:
        _patch_bootstrap(mp, bootstrap)
        for span in llm_spans + agent_spans:
            processor.on_end(span)
        # Multi-node token attach is export-time FIFO (prefer_fifo=True).
        processor.enrich_spans_for_export(llm_spans + agent_spans)

    plugin_in = sum(m.prompt_tokens for m in metrics)
    plugin_out = sum(m.completion_tokens for m in metrics)
    span_in = sum(int(s._attributes.get(ATTR_GEN_AI_IN_TOKENS) or 0) for s in llm_spans)
    span_out = sum(int(s._attributes.get(ATTR_GEN_AI_OUT_TOKENS) or 0) for s in llm_spans)
    agent_in = sum(int(s._attributes.get(ATTR_GEN_AI_IN_TOKENS) or 0) for s in agent_spans)

    assert span_in == plugin_in
    assert span_out == plugin_out
    assert agent_in == 0
