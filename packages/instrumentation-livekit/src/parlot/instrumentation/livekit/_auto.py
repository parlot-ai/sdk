"""
Auto-configuration helpers for parlot-instrumentation-livekit.

``configure()`` is the main entry point. It:
  1. Builds a TracerProvider from env vars (or accepts a BYO provider).
  2. Registers it with livekit.agents.telemetry.
  3. Patches AgentSession to auto-install the handoff hook.

Session identity is bootstrapped automatically on LiveKit's ``job_entrypoint`` span.
Call ``await ctx.connect()`` as usual — room metadata is captured on connect.

Environment variables:
  PARLOT_ENDPOINT         OTLP HTTP endpoint (e.g. http://localhost:4318)
  PARLOT_API_KEY          API key sent as Bearer token in the Authorization header
  PARLOT_CAPTURE_CONTENT  "false" to disable prompt/response capture (default: true)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("parlot.instrumentation.livekit")

_configured = False


def configure(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_content: Optional[bool] = None,
    prices: Optional[dict] = None,
    tracer_provider=None,
) -> None:
    """Configure Parlot instrumentation for a LiveKit Agents application.

    Call once at module import (before starting the worker)::

        from parlot.instrumentation.livekit import configure

        configure()

        from livekit.agents import AgentSession, JobContext, WorkerOptions, cli

        async def entrypoint(ctx: JobContext):
            await ctx.connect()
            ...

    All arguments are optional; configuration falls back to environment
    variables when not provided.

    Args:
        endpoint: OTLP HTTP endpoint. Falls back to ``PARLOT_ENDPOINT``.
        api_key: API key for the Parlot backend. Falls back to ``PARLOT_API_KEY``.
        capture_content: Whether to capture prompt/response text as span events.
            Falls back to ``PARLOT_CAPTURE_CONTENT`` env var (default ``True``).
        prices: Custom model price table passed to ``LiveKitGenAIProcessor``.
            Keys are model name prefixes; values are (input_$/M, output_$/M).
        tracer_provider: Supply your own pre-built ``TracerProvider`` and skip
            auto-construction. The provider is still registered with LiveKit.
            Use this when you need full control (e.g. adding extra processors,
            using a different exporter).
    """
    global _configured
    if _configured:
        logger.debug("parlot-instrumentation.livekit already configured — skipping")
        return

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
            prices=prices,
        )

    from parlot.core.processor import assert_sync_span_processors

    from ._session import set_span_context_attach_enabled

    attach_ok = assert_sync_span_processors(tracer_provider)
    set_span_context_attach_enabled(attach_ok)

    _register_with_livekit(tracer_provider)
    _patch_agent_session_with_tracer(tracer_provider)
    _patch_job_context_connect()
    from ._session_end import patch_agent_server_run

    patch_agent_server_run()

    _configured = True
    logger.debug("parlot-instrumentation.livekit configured (endpoint=%s)", resolved_endpoint)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_provider(
    endpoint: str,
    api_key: str,
    capture_content: bool,
    prices: Optional[dict],
):
    """Build a TracerProvider with LiveKitGenAIProcessor + OTLP exporter."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from opentelemetry import metrics as otel_metrics

    from ._export import QuietOTLPSpanExporter
    from ._metrics import ParlotMetricsRecorder, build_meter_provider
    from ._processor import LiveKitGenAIProcessor
    from ._turn_trace_export import TurnTraceRemappingExporter

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
    otlp_exporter = OTLPSpanExporter(endpoint=trace_endpoint, headers=headers)

    processor = LiveKitGenAIProcessor(
        capture_content=capture_content,
        prices=prices,
    )

    remapping_exporter = TurnTraceRemappingExporter(otlp_exporter, processor)
    exporter = QuietOTLPSpanExporter(
        remapping_exporter,
        endpoint_label=trace_endpoint,
    )

    provider = TracerProvider()
    provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    from parlot.core.processor import assert_sync_span_processors

    from ._session import set_span_context_attach_enabled

    attach_ok = assert_sync_span_processors(provider)
    set_span_context_attach_enabled(attach_ok)

    meter_provider = build_meter_provider(endpoint, headers)
    otel_metrics.set_meter_provider(meter_provider)
    processor.set_tracer(provider.get_tracer("parlot.instrumentation.livekit"))
    processor.set_metrics(ParlotMetricsRecorder(meter_provider))

    return provider


def _register_with_livekit(provider) -> None:
    """Hand the provider to livekit.agents.telemetry."""
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
    """Patch AgentSession using the tracer from our provider."""
    tracer = provider.get_tracer("parlot.instrumentation.livekit")

    from ._hooks import _patch_agent_session

    _patch_agent_session(tracer)


def _patch_job_context_connect() -> None:
    """Stamp ``room_sid`` on the live session span after ``JobContext.connect``."""
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

    _parlot_connect._parlot_connect_patched = True
    JobContext.connect = _parlot_connect
    logger.debug("Patched JobContext.connect for mid-flight room_sid")
