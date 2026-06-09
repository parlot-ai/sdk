"""Auto-configuration helpers for parlot-instrumentation-livekit."""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from typing import Optional

logger = logging.getLogger("parlot.instrumentation.livekit")

_configured = False


def _is_livekit_dev_watch_parent() -> bool:
    """True when this process is LiveKit's dev-mode file-watcher parent.

    ``lk-agents dev`` (reload on by default) imports the agent in a parent
    process that only watches files, then spawns a child worker that
    re-imports ``__main__`` and runs jobs. Instrumentation belongs in the child.

    The spawned child inherits ``sys.argv`` (including ``dev``) and, while
    ``agent.py`` is re-imported during ``multiprocessing`` spawn setup,
    ``parent_process()`` is still ``None``. Use the process name instead:
    only the top-level watcher is ``MainProcess``.
    """
    if multiprocessing.current_process().name != "MainProcess":
        return False

    argv = sys.argv
    if "dev" not in argv:
        return False

    if "--no-reload" in argv:
        return False

    return True


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

    if _is_livekit_dev_watch_parent():
        logger.debug(
            "Skipping parlot-instrumentation.livekit configure in LiveKit dev "
            "watcher parent (worker child will configure)"
        )
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
    _install_telemetry_compare()

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

    from ._export import QuietOTLPSpanExporter
    from ._export_filter import EnrichingExportSpanExporter, ExportFilterSpanExporter
    from ._export_sanitize import SanitizeVendorAttrsSpanExporter
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
    enriching_exporter = EnrichingExportSpanExporter(remapping_exporter, processor)
    filtered_exporter = ExportFilterSpanExporter(enriching_exporter)
    sanitized_exporter = SanitizeVendorAttrsSpanExporter(filtered_exporter)
    exporter = QuietOTLPSpanExporter(
        sanitized_exporter,
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
    # Parlot metrics use a dedicated MeterProvider — do not call
    # otel_metrics.set_meter_provider() so LiveKit's lk.agents.usage.* counters
    # stay on the process default and are not exported to Parlot's pipeline.
    processor.set_tracer(provider.get_tracer("parlot.instrumentation.livekit"))
    processor.set_metrics(ParlotMetricsRecorder(meter_provider))

    provider._parlot_processor = processor  # type: ignore[attr-defined]
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
    processor = getattr(provider, "_parlot_processor", None)
    if processor is None:
        logger.debug("No Parlot processor on provider; skipping AgentSession patch")
        return
    tracer = provider.get_tracer("parlot.instrumentation.livekit")

    from ._hooks import _patch_agent_session
    from ._plugin_metrics import install_emit_metrics_intercept

    _patch_agent_session(processor, tracer)
    install_emit_metrics_intercept(processor)


def _install_telemetry_compare() -> None:
    """Compare JSONL is wired through the production metrics emit intercept."""
    from ._telemetry_compare import compare_enabled

    if compare_enabled():
        logger.debug("PARLOT_TELEMETRY_COMPARE enabled (events/spans via processor hooks)")


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
        from ._session import _run_post_bootstrap_connect, get_job_bootstrap

        if get_job_bootstrap() is None:
            return
        await _run_post_bootstrap_connect(self)

    _parlot_connect._parlot_connect_patched = True
    JobContext.connect = _parlot_connect
    logger.debug("Patched JobContext.connect for room_sid + egress")
