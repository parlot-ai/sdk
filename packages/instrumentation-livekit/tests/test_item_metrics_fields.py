"""Tests for ChatMessage.metrics field normalization (_item_metrics)."""

from __future__ import annotations

from types import SimpleNamespace

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from parlot.instrumentation.livekit._events import _item_metrics
from parlot.instrumentation.livekit._metrics import ParlotMetricsRecorder
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from bootstrap_helpers import bootstrap_via_agent_state


def test_item_metrics_livekit_native_field_names() -> None:
    item = SimpleNamespace(
        metrics=SimpleNamespace(
            e2e_latency=1.5,
            llm_node_ttft=0.25,
            tts_node_ttfb=0.1,
            transcription_delay=0.4,
            end_of_turn_delay=0.2,
            on_user_turn_completed_delay=0.05,
        )
    )
    out = _item_metrics(item)
    assert out["e2e_latency"] == 1.5
    assert out["llm_ttft"] == 0.25
    assert out["tts_ttfb"] == 0.1
    assert out["transcription_delay"] == 0.4
    assert out["eou_delay"] == 0.2
    assert out["on_user_turn_completed_delay"] == 0.05


def test_item_metrics_legacy_aliases() -> None:
    item = SimpleNamespace(
        metrics={"llm_ttft": 0.3, "tts_ttfb": 0.15, "eou_delay": 0.08}
    )
    out = _item_metrics(item)
    assert out["llm_ttft"] == 0.3
    assert out["tts_ttfb"] == 0.15
    assert out["eou_delay"] == 0.08


def test_agent_message_metrics_flow_to_record_turn() -> None:
    from opentelemetry.sdk.trace import TracerProvider

    reader = InMemoryMetricReader()
    provider = TracerProvider()
    proc = LiveKitGenAIProcessor()
    proc.set_tracer(provider.get_tracer("test"))
    proc.set_metrics(ParlotMetricsRecorder(MeterProvider(metric_readers=[reader])))
    bootstrap_via_agent_state(proc, "job-metrics")
    from parlot.instrumentation.livekit._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    assert bootstrap is not None
    bootstrap.state.parlot_session_id = "sess-metrics"

    proc.commit_agent_message(
        "Hello",
        metrics={
            "e2e_latency": 2.0,
            "llm_ttft": 0.5,
            "tts_ttfb": 0.2,
            "eou_delay": 0.1,
        },
    )

    data = reader.get_metrics_data()
    assert data is not None
    histograms = {
        m.name: m
        for scope in data.resource_metrics[0].scope_metrics
        for m in scope.metrics
    }
    assert "turn.e2e_latency_ms" in histograms
    assert "turn.llm_ttft_ms" in histograms
    assert "turn.tts_ttfb_ms" in histograms
    assert "turn.eou_delay_ms" in histograms


def test_conversation_item_livekit_metrics_via_event_bridge() -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from parlot.instrumentation.livekit._events import LiveKitEventBridge

    reader = InMemoryMetricReader()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    proc = LiveKitGenAIProcessor()
    provider.add_span_processor(proc)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    proc.set_tracer(provider.get_tracer("test"))
    proc.set_metrics(ParlotMetricsRecorder(MeterProvider(metric_readers=[reader])))
    bootstrap_via_agent_state(proc, "job-ev-metrics")
    from parlot.instrumentation.livekit._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    assert bootstrap is not None
    bootstrap.state.parlot_session_id = "sess-ev-metrics"

    bridge = LiveKitEventBridge(proc, proc._tracer)
    bridge._on_conversation_item_added(
        SimpleNamespace(
            item=SimpleNamespace(
                id="msg-a-livekit",
                type="message",
                role="assistant",
                text_content="Done",
                interrupted=False,
                metrics=SimpleNamespace(
                    e2e_latency=3.0,
                    llm_node_ttft=0.6,
                    tts_node_ttfb=0.25,
                    end_of_turn_delay=0.12,
                ),
            )
        )
    )

    data = reader.get_metrics_data()
    assert data is not None
    names = {
        m.name
        for scope in data.resource_metrics[0].scope_metrics
        for m in scope.metrics
    }
    assert "turn.llm_ttft_ms" in names
    assert "turn.tts_ttfb_ms" in names
    assert "turn.eou_delay_ms" in names
