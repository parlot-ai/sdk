"""Tests for plugin metrics → OTLP usage.* and llm_node token enrichment."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from parlot.core.attrs import ATTR_GEN_AI_IN_TOKENS, ATTR_GEN_AI_OUT_TOKENS
from parlot.instrumentation.livekit._plugin_metrics import (
    handle_plugin_metrics_collected,
    install_emit_metrics_intercept,
    resolve_llm_usage_for_span,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor


class _FakeMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def record_usage_collected(self, state, metrics_obj) -> None:
        self.calls.append((state, metrics_obj))


def test_handle_plugin_metrics_skips_vad() -> None:
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = SimpleNamespace(parlot_session_id="sess-1")
    bootstrap = SimpleNamespace(state=state)

    with patch(
        "parlot.instrumentation.livekit._session.get_job_bootstrap",
        return_value=bootstrap,
    ):
        vad = SimpleNamespace(type="vad_metrics", audio_duration=1.0)
        handle_plugin_metrics_collected(processor, vad)
    assert processor._metrics.calls == []


def test_handle_plugin_metrics_llm_accumulator() -> None:
    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = SimpleNamespace(parlot_session_id="sess-1")
    bootstrap = SimpleNamespace(state=state)

    with patch(
        "parlot.instrumentation.livekit._session.get_job_bootstrap",
        return_value=bootstrap,
    ):
        llm = SimpleNamespace(
            type="llm_metrics",
            speech_id="sp-42",
            prompt_tokens=100,
            completion_tokens=20,
            metadata=None,
        )
        handle_plugin_metrics_collected(processor, llm)
    assert len(processor._metrics.calls) == 1

    usage = resolve_llm_usage_for_span(processor, speech_id="sp-42")
    assert usage is not None
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 20


def test_enrich_llm_node_applies_plugin_tokens() -> None:
    from test_platform_refs import _FakeSpan

    processor = LiveKitGenAIProcessor()
    processor._metrics = _FakeMetrics()
    state = SimpleNamespace(parlot_session_id="sess-1")

    with patch(
        "parlot.instrumentation.livekit._session.get_job_bootstrap",
        return_value=SimpleNamespace(state=state),
    ):
        llm = SimpleNamespace(
            type="llm_metrics",
            speech_id="",
            prompt_tokens=50,
            completion_tokens=5,
            metadata=None,
        )
        handle_plugin_metrics_collected(processor, llm)

    span = _FakeSpan()
    processor._apply_plugin_llm_usage_to_span(span, span._attributes or {})
    attrs = span._attributes or {}
    assert attrs.get(ATTR_GEN_AI_IN_TOKENS) == 50
    assert attrs.get(ATTR_GEN_AI_OUT_TOKENS) == 5


def test_install_emit_metrics_intercept_patches_once() -> None:
    pytest.importorskip("livekit.agents")
    from livekit.agents import AgentSession

    if not hasattr(AgentSession, "emit"):
        pytest.skip("AgentSession.emit not available in this livekit version")

    AgentSession._parlot_emit_metrics_patched = False  # type: ignore[attr-defined]
    original = AgentSession.emit
    processor = LiveKitGenAIProcessor()
    install_emit_metrics_intercept(processor)
    assert AgentSession.emit is not original
    install_emit_metrics_intercept(processor)
    AgentSession._parlot_emit_metrics_patched = False  # type: ignore[attr-defined]
    AgentSession.emit = original
