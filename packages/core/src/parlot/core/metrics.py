"""Shared OTLP metrics: MeterProvider bootstrap + usage / turn / session instruments.

Adapters map framework events onto :class:`ParlotMetricsRecorder`. Long-lived
hosts (Pipecat) should call :meth:`ParlotMetricsRecorder.shutdown` when a
session ends so the periodic reader does not keep POSTing to ``/v1/metrics``.
"""

from __future__ import annotations

import logging
from typing import Mapping, Optional

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricExportResult,
    MetricsData,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.util.types import AttributeValue

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
from parlot.core.provider import build_parlot_client_headers

logger = logging.getLogger("parlot.core.metrics")

DEFAULT_METRICS_EXPORT_INTERVAL_MS = 5_000
# Long-lived hosts (e.g. Pipecat dev runner) should prefer this and shutdown
# the recorder on session close so idle POSTs stop.
LONG_LIVED_METRICS_EXPORT_INTERVAL_MS = 60_000

ATTR_TENANT_ID = "tenant_id"


class QuietOTLPMetricExporter(MetricExporter):
    """Wraps an OTLP metric exporter with one-line warning logs on failure."""

    def __init__(
        self,
        exporter: MetricExporter,
        *,
        endpoint_label: str,
    ) -> None:
        super().__init__(
            preferred_temporality=exporter._preferred_temporality,
            preferred_aggregation=exporter._preferred_aggregation,
        )
        self._exporter = exporter
        self._endpoint_label = endpoint_label

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs,
    ) -> MetricExportResult:
        try:
            result = self._exporter.export(
                metrics_data, timeout_millis=timeout_millis, **kwargs
            )
            if result == MetricExportResult.FAILURE:
                logger.warning(
                    "Parlot metrics export returned FAILURE (%s)",
                    self._endpoint_label,
                )
            return result
        except Exception as exc:
            msg = str(exc).strip() or exc.__class__.__name__
            if len(msg) > 240:
                msg = msg[:237] + "..."
            logger.warning(
                "Parlot metrics export failed (%s): %s",
                self._endpoint_label,
                msg,
            )
            return MetricExportResult.FAILURE

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self._exporter.force_flush(timeout_millis=timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        self._exporter.shutdown(timeout_millis=timeout_millis, **kwargs)


def build_parlot_meter_provider(
    endpoint: str,
    resource: Resource,
    *,
    api_key: str = "",
    headers: Optional[Mapping[str, str]] = None,
    export_interval_millis: int = DEFAULT_METRICS_EXPORT_INTERVAL_MS,
    quiet: bool = True,
) -> MeterProvider:
    """Build a dedicated MeterProvider exporting Parlot metrics.

    Do **not** register this as the global meter provider when the host
    framework also emits its own meters (LiveKit ``lk.agents.usage.*``).
    """
    metrics_endpoint = endpoint.rstrip("/") + "/v1/metrics"
    resolved_headers = (
        dict(headers) if headers is not None else build_parlot_client_headers(api_key)
    )
    raw = OTLPMetricExporter(endpoint=metrics_endpoint, headers=resolved_headers)
    exporter: MetricExporter = (
        QuietOTLPMetricExporter(raw, endpoint_label=metrics_endpoint)
        if quiet
        else raw
    )
    reader = PeriodicExportingMetricReader(
        exporter, export_interval_millis=int(export_interval_millis)
    )
    return MeterProvider(metric_readers=[reader], resource=resource)


class ParlotMetricsRecorder:
    """Records Parlot ``usage.*``, ``turn.*``, and ``session.*`` instruments."""

    def __init__(
        self,
        meter_provider: MeterProvider,
        *,
        meter_name: str = "parlot.core",
        framework: str = "",
        tenant_id: str = "",
    ) -> None:
        self._meter_provider = meter_provider
        self._framework = (framework or "").strip()
        self._tenant_id = (tenant_id or "").strip()
        meter = meter_provider.get_meter(meter_name)
        self._meter = meter

        self._usage_stt = meter.create_counter(
            METRIC_USAGE_STT_AUDIO_DURATION,
            unit="s",
            description="STT audio duration per usage event",
        )
        self._usage_tts_audio = meter.create_counter(
            METRIC_USAGE_TTS_AUDIO_DURATION,
            unit="s",
            description="TTS audio duration per usage event",
        )
        self._usage_tts_chars = meter.create_counter(
            METRIC_USAGE_TTS_CHARACTERS,
            description="TTS characters synthesized per usage event",
        )
        self._usage_llm_in = meter.create_counter(
            METRIC_USAGE_LLM_INPUT_TOKENS,
            description="LLM input tokens per usage event",
        )
        self._usage_llm_out = meter.create_counter(
            METRIC_USAGE_LLM_OUTPUT_TOKENS,
            description="LLM output tokens per usage event",
        )

        self._turn_e2e = meter.create_histogram(
            "turn.e2e_latency_ms",
            unit="ms",
            description="End-to-end latency for one agent turn",
        )
        self._turn_llm_ttft = meter.create_histogram(
            "turn.llm_ttft_ms",
            unit="ms",
            description="LLM time to first token for one agent turn",
        )
        self._turn_tts_ttfb = meter.create_histogram(
            "turn.tts_ttfb_ms",
            unit="ms",
            description="TTS time to first byte for one agent turn",
        )
        self._turn_transcription_delay = meter.create_histogram(
            "turn.transcription_delay_ms",
            unit="ms",
            description="Speech end to transcript available for one agent turn",
        )
        self._turn_eou_delay = meter.create_histogram(
            "turn.eou_delay_ms",
            unit="ms",
            description="End-of-utterance detection delay for one agent turn",
        )
        self._turn_playback_latency = meter.create_histogram(
            "turn.playback_latency_ms",
            unit="ms",
            description="Playback latency for one agent turn",
        )

        self._session_turns = meter.create_counter(
            "session.turn_count",
            description="Total turns in a session",
        )
        self._session_input_tokens = meter.create_counter(
            "session.total_input_tokens",
            description="Total input tokens in session",
        )
        self._session_output_tokens = meter.create_counter(
            "session.total_output_tokens",
            description="Total output tokens in session",
        )

    @property
    def meter_provider(self) -> MeterProvider:
        return self._meter_provider

    @property
    def meter(self):
        return self._meter

    def _base_attrs(
        self,
        *,
        session_id: str,
        model: str = "",
        provider: str = "",
        framework: str = "",
        participant_role: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> dict[str, AttributeValue]:
        attrs: dict[str, AttributeValue] = {
            ATTR_SESSION_ID: session_id,
        }
        fw = (framework or self._framework).strip()
        if fw:
            attrs[ATTR_AGENT_FRAMEWORK] = fw
        if self._tenant_id:
            attrs[ATTR_TENANT_ID] = self._tenant_id
        if model:
            attrs[ATTR_GEN_AI_MODEL] = model
        if provider:
            attrs[ATTR_GEN_AI_PROVIDER] = provider
        if participant_role:
            attrs[ATTR_TURN_PARTICIPANT_ROLE] = participant_role
        if extra:
            attrs.update(dict(extra))
        return attrs

    def record_stt_audio(
        self,
        *,
        session_id: str,
        audio_seconds: float,
        model: str = "",
        provider: str = "",
        framework: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> None:
        if not session_id or audio_seconds <= 0:
            return
        self._usage_stt.add(
            float(audio_seconds),
            attributes=self._base_attrs(
                session_id=session_id,
                model=model,
                provider=provider,
                framework=framework,
                extra=extra,
            ),
        )

    def record_tts_audio(
        self,
        *,
        session_id: str,
        audio_seconds: float,
        model: str = "",
        provider: str = "",
        framework: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> None:
        if not session_id or audio_seconds <= 0:
            return
        self._usage_tts_audio.add(
            float(audio_seconds),
            attributes=self._base_attrs(
                session_id=session_id,
                model=model,
                provider=provider,
                framework=framework,
                extra=extra,
            ),
        )

    def record_tts_characters(
        self,
        *,
        session_id: str,
        characters: int,
        model: str = "",
        provider: str = "",
        framework: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> None:
        if not session_id or characters <= 0:
            return
        self._usage_tts_chars.add(
            int(characters),
            attributes=self._base_attrs(
                session_id=session_id,
                model=model,
                provider=provider,
                framework=framework,
                extra=extra,
            ),
        )

    def record_llm_tokens(
        self,
        *,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
        provider: str = "",
        framework: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> None:
        if not session_id:
            return
        attrs = self._base_attrs(
            session_id=session_id,
            model=model,
            provider=provider,
            framework=framework,
            extra=extra,
        )
        if input_tokens > 0:
            self._usage_llm_in.add(int(input_tokens), attributes=attrs)
        if output_tokens > 0:
            self._usage_llm_out.add(int(output_tokens), attributes=attrs)

    def record_turn(
        self,
        *,
        session_id: str,
        turn_index: int,
        participant_role: str = "agent",
        e2e_latency_s: Optional[float] = None,
        llm_ttft_s: Optional[float] = None,
        tts_ttfb_s: Optional[float] = None,
        transcription_delay_s: Optional[float] = None,
        eou_delay_s: Optional[float] = None,
        playback_latency_s: Optional[float] = None,
        interrupted: bool = False,
        framework: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> None:
        if not session_id:
            return
        attrs = self._base_attrs(
            session_id=session_id,
            framework=framework,
            participant_role=participant_role,
            extra=extra,
        )
        attrs[ATTR_TURN_INDEX] = int(turn_index)
        if interrupted:
            attrs[ATTR_TURN_INTERRUPTED] = True
        if e2e_latency_s is not None:
            self._turn_e2e.record(float(e2e_latency_s) * 1000.0, attributes=attrs)
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

    def record_session_close(
        self,
        *,
        session_id: str,
        turn_count: int = 0,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        framework: str = "",
        extra: Optional[Mapping[str, AttributeValue]] = None,
    ) -> None:
        if not session_id:
            return
        attrs = self._base_attrs(
            session_id=session_id, framework=framework, extra=extra
        )
        if turn_count:
            self._session_turns.add(int(turn_count), attributes=attrs)
        if total_input_tokens:
            self._session_input_tokens.add(int(total_input_tokens), attributes=attrs)
        if total_output_tokens:
            self._session_output_tokens.add(int(total_output_tokens), attributes=attrs)

    def force_flush(self, timeout_millis: int = 5_000) -> bool:
        try:
            return bool(self._meter_provider.force_flush(timeout_millis))
        except Exception:
            return False

    def shutdown(self, timeout_millis: int = 5_000) -> None:
        """Flush and stop periodic export. Safe to call more than once."""
        try:
            self.force_flush(timeout_millis)
        except Exception:
            pass
        try:
            self._meter_provider.shutdown(timeout_millis=timeout_millis)
        except Exception:
            logger.debug("MeterProvider shutdown failed", exc_info=True)


# Back-compat alias used during the Pipecat thin-wrapper transition.
UsageMetricsRecorder = ParlotMetricsRecorder
