"""Auto-configuration helpers for parlot-instrumentation-livekit."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("parlot.instrumentation.livekit")

_configured = False


def _configure_parlot_logging() -> None:
    level_name = os.getenv("PARLOT_DEBUG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not logging.root.handlers:
        logging.basicConfig(level=level)


def configure(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider=None,
) -> None:
    global _configured
    if _configured:
        logger.debug("parlot-instrumentation.livekit already configured — skipping")
        return

    _configure_parlot_logging()

    resolved_endpoint = endpoint or os.environ.get("PARLOT_ENDPOINT", "")
    resolved_api_key = api_key or os.environ.get("PARLOT_API_KEY", "")

    if capture_content is None:
        env_val = os.environ.get("PARLOT_CAPTURE_CONTENT", "").lower()
        capture_content = env_val not in ("false", "0", "no")

    if tracer_provider is None:
        if not resolved_endpoint:
            raise ValueError(
                "No OTLP endpoint configured. Pass endpoint= or set the "
                "PARLOT_ENDPOINT environment variable."
            )
        tracer_provider = _build_provider(
            endpoint=resolved_endpoint,
            api_key=resolved_api_key,
            capture_content=capture_content,
            service_name=service_name,
        )

    from parlot.core.processor import assert_sync_span_processors

    from ._session import set_span_context_attach_enabled

    attach_ok = assert_sync_span_processors(tracer_provider)
    set_span_context_attach_enabled(attach_ok)

    _register_with_livekit(tracer_provider)
    _patch_agent_session_with_tracer(tracer_provider)
    _patch_job_context_connect()

    if resolved_api_key:
        _fetch_and_cache_bootstrap(resolved_endpoint, resolved_api_key)

    _configured = True
    logger.debug("parlot-instrumentation.livekit configured (endpoint=%s)", resolved_endpoint)


def _fetch_and_cache_bootstrap(endpoint: str, api_key: str) -> None:
    import httpx

    from ._runtime_context import apply_bootstrap_payload

    url = f"{endpoint.rstrip('/')}/v1/telemetry/bootstrap"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "parlot: telemetry bootstrap failed status=%s",
                resp.status_code,
            )
            return
        recording_ready = apply_bootstrap_payload(endpoint, api_key, resp.json())
        if recording_ready:
            logger.debug("parlot: telemetry bootstrap cached (recording enabled)")
        else:
            logger.debug(
                "parlot: telemetry bootstrap cached (instrumentation only; "
                "configure LiveKit integration to enable recording)"
            )
    except Exception:
        logger.exception("parlot: telemetry bootstrap request failed")


def _build_provider(
    endpoint: str,
    api_key: str,
    capture_content: bool,
    service_name: Optional[str],
):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.semconv.attributes import service_attributes

    from opentelemetry import metrics as otel_metrics

    from ._export import QuietOTLPSpanExporter
    from ._export_filter import ExportFilterSpanExporter
    from ._metrics import ParlotMetricsRecorder, build_meter_provider
    from ._processor import LiveKitGenAIProcessor
    from ._turn_trace_export import TurnTraceRemappingExporter

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resource = Resource.create(
        {service_attributes.SERVICE_NAME: service_name or "unknown"}
    )

    trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
    otlp_exporter = OTLPSpanExporter(endpoint=trace_endpoint, headers=headers)

    processor = LiveKitGenAIProcessor(
        capture_content=capture_content,
    )

    remapping_exporter = TurnTraceRemappingExporter(otlp_exporter, processor)
    filtered_exporter = ExportFilterSpanExporter(remapping_exporter)
    exporter = QuietOTLPSpanExporter(
        filtered_exporter,
        endpoint_label=trace_endpoint,
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    from parlot.core.processor import assert_sync_span_processors

    from ._session import set_span_context_attach_enabled

    attach_ok = assert_sync_span_processors(provider)
    set_span_context_attach_enabled(attach_ok)

    meter_provider = build_meter_provider(endpoint, headers, resource)
    otel_metrics.set_meter_provider(meter_provider)
    processor.set_tracer(provider.get_tracer("parlot.instrumentation.livekit"))
    processor.set_metrics(ParlotMetricsRecorder(meter_provider))

    return provider


def _register_with_livekit(provider) -> None:
    try:
        from livekit.agents import telemetry as _lk_telemetry

        _lk_telemetry.set_tracer_provider(provider)
        logger.debug("Registered TracerProvider with livekit.agents.telemetry")
    except ImportError:
        logger.debug(
            "livekit-agents not importable; provider NOT registered with LiveKit. "
            "Install livekit-agents or register the provider manually."
        )


def _patch_agent_session_with_tracer(provider) -> None:
    tracer = provider.get_tracer("parlot.instrumentation.livekit")

    from ._hooks import _patch_agent_session

    _patch_agent_session(tracer)


def _patch_job_context_connect() -> None:
    try:
        from livekit.agents import JobContext
    except ImportError:
        logger.debug("livekit-agents not importable; JobContext.connect not patched")
        return

    if getattr(JobContext.connect, "_parlot_connect_patched", False):
        return

    _orig_connect = JobContext.connect

    async def _parlot_connect(self, *args, **kwargs):
        await _orig_connect(self, *args, **kwargs)
        from ._session import refresh_bootstrap_room_from_ctx

        await refresh_bootstrap_room_from_ctx(self)
        from ._egress import maybe_start_room_composite_egress

        await maybe_start_room_composite_egress(self)

    _parlot_connect._parlot_connect_patched = True
    JobContext.connect = _parlot_connect
    logger.debug("Patched JobContext.connect for room_sid + egress")
