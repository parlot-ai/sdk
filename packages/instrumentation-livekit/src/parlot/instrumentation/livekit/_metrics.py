"""OTLP metrics for Parlot session / turn aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

from ._export import QuietOTLPMetricExporter
from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_SESSION_ID,
    ATTR_TURN_INDEX,
    ATTR_TURN_INTERRUPTED,
    ATTR_TURN_PARTICIPANT_ROLE,
)
from parlot.core.runtime import get_runtime

if TYPE_CHECKING:
    from ._processor import _LiveKitSessionState

ATTR_ORG_ID = "org_id"


def build_meter_provider(
    endpoint: str,
    headers: dict[str, str],
    resource: Resource,
) -> MeterProvider:
    metrics_endpoint = endpoint.rstrip("/") + "/v1/metrics"
    exporter = QuietOTLPMetricExporter(
        OTLPMetricExporter(endpoint=metrics_endpoint, headers=headers),
        endpoint_label=metrics_endpoint,
    )
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5_000)
    return MeterProvider(metric_readers=[reader], resource=resource)


class ParlotMetricsRecorder:
    """Records turn.* and session.* metrics mapped to Parlot metric names."""

    def __init__(self, meter_provider: MeterProvider) -> None:
        self._meter = meter_provider.get_meter("parlot.instrumentation.livekit")
        self._turn_e2e = self._meter.create_histogram(
            "turn.e2e_latency_ms",
            unit="ms",
            description="End-to-end latency for one agent turn",
        )
        self._turn_llm_ttft = self._meter.create_histogram(
            "turn.llm_ttft_ms",
            unit="ms",
            description="LLM time to first token for one agent turn",
        )
        self._turn_tts_ttfb = self._meter.create_histogram(
            "turn.tts_ttfb_ms",
            unit="ms",
            description="TTS time to first byte for one agent turn",
        )
        self._turn_transcription_delay = self._meter.create_histogram(
            "turn.transcription_delay_ms",
            unit="ms",
            description="Speech end to transcript available for one agent turn",
        )
        self._turn_eou_delay = self._meter.create_histogram(
            "turn.eou_delay_ms",
            unit="ms",
            description="End-of-utterance detection delay for one agent turn",
        )
        self._session_turns = self._meter.create_counter(
            "session.turn_count",
            description="Total turns in a session",
        )
        self._session_input_tokens = self._meter.create_counter(
            "session.total_input_tokens",
            description="Total input tokens in session",
        )
        self._session_output_tokens = self._meter.create_counter(
            "session.total_output_tokens",
            description="Total output tokens in session",
        )

    def _base_attrs(
        self,
        state: "_LiveKitSessionState",
        *,
        participant_role: str = "",
    ) -> dict[str, object]:
        attrs: dict[str, object] = {
            ATTR_SESSION_ID: state.parlot_session_id,
            ATTR_AGENT_FRAMEWORK: "livekit",
        }
        runtime = get_runtime()
        if runtime is not None and runtime.org_id:
            attrs[ATTR_ORG_ID] = runtime.org_id
        if participant_role:
            attrs[ATTR_TURN_PARTICIPANT_ROLE] = participant_role
        return attrs

    def record_turn(
        self,
        state: "_LiveKitSessionState",
        *,
        e2e_latency_s: Optional[float] = None,
        llm_ttft_s: Optional[float] = None,
        tts_ttfb_s: Optional[float] = None,
        transcription_delay_s: Optional[float] = None,
        eou_delay_s: Optional[float] = None,
        interrupted: bool = False,
        participant_role: str = "agent",
    ) -> None:
        attrs = {
            **self._base_attrs(state, participant_role=participant_role),
            ATTR_TURN_INDEX: state.turn_count,
        }
        if interrupted:
            attrs[ATTR_TURN_INTERRUPTED] = True
        if e2e_latency_s is not None:
            self._turn_e2e.record(e2e_latency_s * 1000.0, attributes=attrs)
        if llm_ttft_s is not None:
            self._turn_llm_ttft.record(float(llm_ttft_s) * 1000.0, attributes=attrs)
        if tts_ttfb_s is not None:
            self._turn_tts_ttfb.record(float(tts_ttfb_s) * 1000.0, attributes=attrs)
        if transcription_delay_s is not None:
            self._turn_transcription_delay.record(
                float(transcription_delay_s) * 1000.0, attributes=attrs
            )
        if eou_delay_s is not None:
            self._turn_eou_delay.record(float(eou_delay_s) * 1000.0, attributes=attrs)

    def record_session_close(self, state: "_LiveKitSessionState") -> None:
        attrs = self._base_attrs(state)
        if state.turn_count:
            self._session_turns.add(state.turn_count, attributes=attrs)
        if state.total_input_tokens:
            self._session_input_tokens.add(
                state.total_input_tokens, attributes=attrs
            )
        if state.total_output_tokens:
            self._session_output_tokens.add(
                state.total_output_tokens, attributes=attrs
            )
