"""Tests for Parlot usage.* metric emission from LiveKit MetricsCollected."""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace
from typing import cast

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_PROVIDER,
    ATTR_SESSION_ID,
    METRIC_USAGE_LLM_INPUT_TOKENS,
    METRIC_USAGE_LLM_OUTPUT_TOKENS,
    METRIC_USAGE_STT_AUDIO_DURATION,
    METRIC_USAGE_TTS_AUDIO_DURATION,
    METRIC_USAGE_TTS_CHARACTERS,
)
from parlot.instrumentation.livekit._metrics import ParlotMetricsRecorder
from parlot.instrumentation.livekit._processor import _LiveKitSessionState


def _usage_state(session_id: str) -> _LiveKitSessionState:
    return _LiveKitSessionState(parlot_session_id=session_id)


def _point_value(point: object) -> float | None:
    value = getattr(point, "value", None)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _metric_sums(reader: InMemoryMetricReader) -> dict[str, float]:
    data = reader.get_metrics_data()
    totals: dict[str, float] = {}
    if data is None:
        return totals
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                total = 0.0
                for point in metric.data.data_points:
                    value = _point_value(point)
                    if value is not None:
                        total += value
                totals[metric.name] = totals.get(metric.name, 0.0) + total
    return totals


def test_record_usage_collected_llm() -> None:
    reader = InMemoryMetricReader()
    recorder = ParlotMetricsRecorder(MeterProvider(metric_readers=[reader]))
    state = _usage_state("sess-usage-1")
    llm = SimpleNamespace(
        type="llm_metrics",
        prompt_tokens=100,
        completion_tokens=50,
        metadata=SimpleNamespace(model_name="gpt-4o", model_provider="openai"),
    )

    recorder.record_usage_collected(state, llm)
    totals = _metric_sums(reader)

    assert totals[METRIC_USAGE_LLM_INPUT_TOKENS] == 100
    assert totals[METRIC_USAGE_LLM_OUTPUT_TOKENS] == 50


def test_record_usage_collected_stt_tts() -> None:
    reader = InMemoryMetricReader()
    recorder = ParlotMetricsRecorder(MeterProvider(metric_readers=[reader]))
    state = _usage_state("sess-usage-2")

    stt = SimpleNamespace(
        type="stt_metrics",
        audio_duration=3.5,
        metadata=SimpleNamespace(model_name="nova-2", model_provider="deepgram"),
    )
    tts = SimpleNamespace(
        type="tts_metrics",
        audio_duration=2.0,
        characters_count=120,
        metadata=SimpleNamespace(model_name="eleven_flash", model_provider="elevenlabs"),
    )

    recorder.record_usage_collected(state, stt)
    recorder.record_usage_collected(state, tts)
    totals = _metric_sums(reader)

    assert totals[METRIC_USAGE_STT_AUDIO_DURATION] == 3.5
    assert totals[METRIC_USAGE_TTS_AUDIO_DURATION] == 2.0
    assert totals[METRIC_USAGE_TTS_CHARACTERS] == 120


def test_usage_attrs_include_semconv_keys() -> None:
    reader = InMemoryMetricReader()
    recorder = ParlotMetricsRecorder(MeterProvider(metric_readers=[reader]))
    state = _usage_state("sess-usage-3")
    llm = SimpleNamespace(
        type="llm_metrics",
        prompt_tokens=1,
        completion_tokens=0,
        metadata=SimpleNamespace(model_name="gpt-4o-mini", model_provider="openai"),
    )

    recorder.record_usage_collected(state, llm)
    data = reader.get_metrics_data()
    assert data is not None
    point = data.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points[0]
    attrs = cast(Mapping[str, AttributeValue], point.attributes)
    assert attrs[ATTR_SESSION_ID] == "sess-usage-3"
    assert attrs[ATTR_GEN_AI_MODEL] == "gpt-4o-mini"
    assert attrs[ATTR_GEN_AI_PROVIDER] == "openai"
