"""OTLP metrics for Parlot session / turn aggregates (LiveKit)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource

from parlot.core.context import ParlotContext
from parlot.core.metrics import ParlotMetricsRecorder as CoreParlotMetricsRecorder
from parlot.core.metrics import build_parlot_meter_provider

if TYPE_CHECKING:
    from ._session_state import _LiveKitSessionState


def build_meter_provider(
    endpoint: str,
    headers: dict[str, str],
    resource: Resource,
) -> MeterProvider:
    return build_parlot_meter_provider(
        endpoint,
        resource,
        headers=headers,
        export_interval_millis=5_000,
        quiet=True,
    )


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


class ParlotMetricsRecorder(CoreParlotMetricsRecorder):
    """Core metrics + LiveKit ``AgentMetrics`` → ``usage.*`` mapping."""

    def __init__(
        self,
        meter_provider: MeterProvider,
        *,
        context: ParlotContext | None = None,
    ) -> None:
        tenant_id = ""
        runtime = context.runtime if context is not None else None
        if runtime is not None and runtime.tenant_id:
            tenant_id = runtime.tenant_id
        super().__init__(
            meter_provider,
            meter_name="parlot.instrumentation.livekit",
            framework="livekit",
            tenant_id=tenant_id,
        )
        self._context = context

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
        sid = state.parlot_session_id

        if metric_type == "llm_metrics":
            prompt = int(getattr(metrics_obj, "prompt_tokens", 0) or 0)
            completion = int(getattr(metrics_obj, "completion_tokens", 0) or 0)
            self.record_llm_tokens(
                session_id=sid,
                input_tokens=prompt,
                output_tokens=completion,
                model=model_name,
                provider=model_provider,
            )
            return

        if metric_type == "stt_metrics":
            audio_duration = float(getattr(metrics_obj, "audio_duration", 0) or 0)
            self.record_stt_audio(
                session_id=sid,
                audio_seconds=audio_duration,
                model=model_name,
                provider=model_provider,
            )
            return

        if metric_type == "tts_metrics":
            audio_duration = float(getattr(metrics_obj, "audio_duration", 0) or 0)
            characters = int(getattr(metrics_obj, "characters_count", 0) or 0)
            self.record_tts_audio(
                session_id=sid,
                audio_seconds=audio_duration,
                model=model_name,
                provider=model_provider,
            )
            self.record_tts_characters(
                session_id=sid,
                characters=characters,
                model=model_name,
                provider=model_provider,
            )

    def record_turn(  # type: ignore[override]
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
        super().record_turn(
            session_id=state.parlot_session_id,
            turn_index=state.turn_count,
            participant_role=participant_role,
            e2e_latency_s=e2e_latency_s,
            llm_ttft_s=llm_ttft_s,
            tts_ttfb_s=tts_ttfb_s,
            transcription_delay_s=transcription_delay_s,
            eou_delay_s=eou_delay_s,
            playback_latency_s=playback_latency_s,
            interrupted=interrupted,
        )

    def record_session_close(  # type: ignore[override]
        self, state: "_LiveKitSessionState"
    ) -> None:
        super().record_session_close(
            session_id=state.parlot_session_id,
            turn_count=state.turn_count,
            total_input_tokens=state.total_input_tokens,
            total_output_tokens=state.total_output_tokens,
        )
