"""OTLP metrics for Parlot session / turn aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.util.types import AttributeValue

from ._export import QuietOTLPMetricExporter
from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_PROVIDER,
    ATTR_SESSION_ID,
    ATTR_TURN_INDEX,
    ATTR_TURN_INTERRUPTED,
    ATTR_TURN_PARTICIPANT_ROLE,
    METRIC_USAGE_LLM_INPUT_TOKENS,
    METRIC_USAGE_LLM_OUTPUT_TOKENS,
    METRIC_USAGE_STT_AUDIO_DURATION,
    METRIC_USAGE_TTS_AUDIO_DURATION,
    METRIC_USAGE_TTS_CHARACTERS,
)
from parlot.core.runtime import get_runtime

if TYPE_CHECKING:
    from ._session_state import _LiveKitSessionState

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


def _usage_metadata(metrics_obj: Any) -> tuple[str, str]:
    metadata = getattr(metrics_obj, "metadata", None)
    if metadata is None:
        return "", ""
    model_name = getattr(metadata, "model_name", None)
    model_provider = getattr(metadata, "model_provider", None)
    return (
        str(model_name).strip() if model_name else "",
        str(model_provider).strip() if model_provider else "",
    )


class ParlotMetricsRecorder:
    """Records turn.*, session.*, and usage.* metrics mapped to Parlot metric names."""

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
        self._turn_playback_latency = self._meter.create_histogram(
            "turn.playback_latency_ms",
            unit="ms",
            description="Playback latency for one agent turn",
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
        self._usage_llm_input = self._meter.create_counter(
            METRIC_USAGE_LLM_INPUT_TOKENS,
            description="LLM input tokens per usage event",
        )
        self._usage_llm_output = self._meter.create_counter(
            METRIC_USAGE_LLM_OUTPUT_TOKENS,
            description="LLM output tokens per usage event",
        )
        self._usage_stt_audio = self._meter.create_counter(
            METRIC_USAGE_STT_AUDIO_DURATION,
            unit="s",
            description="STT audio duration per usage event",
        )
        self._usage_tts_audio = self._meter.create_counter(
            METRIC_USAGE_TTS_AUDIO_DURATION,
            unit="s",
            description="TTS audio duration per usage event",
        )
        self._usage_tts_characters = self._meter.create_counter(
            METRIC_USAGE_TTS_CHARACTERS,
            description="TTS characters synthesized per usage event",
        )

    def _base_attrs(
        self,
        state: "_LiveKitSessionState",
        *,
        participant_role: str = "",
    ) -> dict[str, AttributeValue]:
        attrs: dict[str, AttributeValue] = {
            ATTR_SESSION_ID: state.parlot_session_id,
            ATTR_AGENT_FRAMEWORK: "livekit",
        }
        runtime = get_runtime()
        if runtime is not None and runtime.org_id:
            attrs[ATTR_ORG_ID] = runtime.org_id
        if participant_role:
            attrs[ATTR_TURN_PARTICIPANT_ROLE] = participant_role
        return attrs

    def _usage_attrs(
        self,
        state: "_LiveKitSessionState",
        model_name: str,
        model_provider: str,
    ) -> dict[str, AttributeValue]:
        attrs = self._base_attrs(state)
        if model_name:
            attrs[ATTR_GEN_AI_MODEL] = model_name
        if model_provider:
            attrs[ATTR_GEN_AI_PROVIDER] = model_provider
        return attrs

    def record_usage_collected(
        self,
        state: "_LiveKitSessionState",
        metrics_obj: Any,
    ) -> None:
        """Map LiveKit AgentMetrics to Parlot usage.* counters."""
        if not state.parlot_session_id:
            return

        metric_type = str(getattr(metrics_obj, "type", "") or "")
        model_name, model_provider = _usage_metadata(metrics_obj)
        attrs = self._usage_attrs(state, model_name, model_provider)

        if metric_type == "llm_metrics":
            prompt = int(getattr(metrics_obj, "prompt_tokens", 0) or 0)
            completion = int(getattr(metrics_obj, "completion_tokens", 0) or 0)
            if prompt:
                self._usage_llm_input.add(prompt, attributes=attrs)
            if completion:
                self._usage_llm_output.add(completion, attributes=attrs)
            return

        if metric_type == "stt_metrics":
            audio_duration = float(getattr(metrics_obj, "audio_duration", 0) or 0)
            if audio_duration > 0:
                self._usage_stt_audio.add(audio_duration, attributes=attrs)
            return

        if metric_type == "tts_metrics":
            audio_duration = float(getattr(metrics_obj, "audio_duration", 0) or 0)
            characters = int(getattr(metrics_obj, "characters_count", 0) or 0)
            if audio_duration > 0:
                self._usage_tts_audio.add(audio_duration, attributes=attrs)
            if characters:
                self._usage_tts_characters.add(characters, attributes=attrs)

    def record_turn(
        self,
        state: "_LiveKitSessionState",
        *,
        e2e_latency_s: Optional[float] = None,
        llm_ttft_s: Optional[float] = None,
        tts_ttfb_s: Optional[float] = None,
        transcription_delay_s: Optional[float] = None,
        eou_delay_s: Optional[float] = None,
        playback_latency_s: Optional[float] = None,
        interrupted: bool = False,
        participant_role: str = "agent",
    ) -> None:
        attrs: dict[str, AttributeValue] = {
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
        if playback_latency_s is not None:
            self._turn_playback_latency.record(
                float(playback_latency_s) * 1000.0, attributes=attrs
            )

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
