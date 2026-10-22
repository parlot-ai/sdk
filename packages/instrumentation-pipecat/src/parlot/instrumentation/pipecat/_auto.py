"""Auto-configuration helpers for parlot-instrumentation-pipecat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from opentelemetry.trace import TracerProvider

from parlot.core.context import ParlotContext

logger = logging.getLogger("parlot.instrumentation.pipecat")

_configured = False
_configured_agent_id: str | None = None
_configured_agent_version: str = ""
_parlot_context: ParlotContext | None = None


def parlotize(
    agent_id: str,
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider: TracerProvider | None = None,
    version: Optional[str] = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> ParlotContext:
    """Parlotize Pipecat instrumentation and OTLP export.

    Call before constructing ``Pipeline`` / ``PipelineWorker``. Builds a
    ``TracerProvider`` with an OTLP exporter (unless one is adopted), registers
    it as the global provider (so Pipecat's ``enable_tracing=True`` path uses
    it), and patches ``PipelineWorker`` to default metrics + turn tracing on.

    Do **not** call Pipecat's ``setup_tracing()`` afterward — it replaces the
    global provider and would drop Parlot processors. ``parlotize`` is the
    Parlot equivalent of that setup.

    Shared parameters match every adapter — see ``parlot.core.ParlotizeProtocol``.

    Args:
        agent_id: Shared — required canonical ``session.agent_id``.
        endpoint: Shared — Parlot OTLP base URL (or ``PARLOT_ENDPOINT``).
        api_key: Shared — org API key (or ``PARLOT_API_KEY``).
        capture_genai_content: Shared — GenAI payload capture override.
        service_name: Shared — OTel ``service.name`` (defaults to ``agent_id``).
        tracer_provider: Shared — existing ``TracerProvider``, or build one.
        version: Shared — ``gen_ai.agent.version``.
        capture_logs: Shared — session log capture.
        log_level: Shared — minimum level for session log capture.

    Returns:
        The ``ParlotContext`` for this process.
    """
    global _configured, _configured_agent_id, _configured_agent_version, _parlot_context
    if _configured:
        logger.debug("parlot-instrumentation.pipecat already configured — skipping")
        assert _parlot_context is not None
        return _parlot_context

    from parlot.core import base_parlotize
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    _configured_agent_version = (version or "").strip() or "unknown"

    res = base_parlotize(
        agent_id,
        endpoint=endpoint,
        api_key=api_key,
        capture_genai_content=capture_genai_content,
        tracer_provider=tracer_provider,
        version=_configured_agent_version,
        capture_logs=capture_logs,
        log_level=log_level,
    )
    _parlot_context = res.context
    _configured_agent_id = res.agent_id

    tracer_provider = res.tracer_provider
    if tracer_provider is None:
        if not res.endpoint:
            raise ValueError(
                "No OTLP endpoint configured. Pass endpoint= or set the "
                "PARLOT_ENDPOINT environment variable."
            )
        tracer_provider = _build_provider(
            endpoint=res.endpoint,
            api_key=res.api_key,
            service_name=service_name or res.agent_id,
            service_version=_configured_agent_version or None,
            context=res.context,
        )
    else:
        # Adopt existing provider: still attach our processor when possible.
        _attach_processor_if_needed(tracer_provider, res.context)

    from opentelemetry import trace

    try:
        trace.set_tracer_provider(tracer_provider)
    except Exception:
        logger.debug("Could not set global tracer provider", exc_info=True)

    from ._hooks import install_pipeline_worker_hooks
    from ._session import set_identity, set_tracer

    set_identity(_configured_agent_id, _configured_agent_version)
    set_tracer(
        tracer_provider.get_tracer(
            "parlot.instrumentation.pipecat",
            resolve_parlot_sdk_version() or None,
        )
    )
    install_pipeline_worker_hooks()
    _neutralize_pipecat_setup_tracing()

    _configured = True
    if not res.endpoint or not res.api_key:
        logger.warning(
            "parlot: pipecat instrumentation installed but telemetry may not "
            "authenticate (agent_id=%s endpoint=%s); check PARLOT_ENDPOINT / "
            "PARLOT_API_KEY",
            res.agent_id,
            res.endpoint or "(unset)",
        )
    else:
        logger.info(
            "parlot: pipecat instrumentation ready (agent_id=%s endpoint=%s)",
            res.agent_id,
            res.endpoint,
        )
    return res.context


def _build_provider(
    *,
    endpoint: str,
    api_key: str,
    service_name: Optional[str],
    service_version: Optional[str] = None,
    context: ParlotContext,
):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from parlot.core.export import ExportFilterSpanExporter
    from parlot.core.provider import build_otlp_http_exporter, build_resource

    from ._processor import PipecatGenAIProcessor

    resource = build_resource(
        service_name=service_name or "pipecat-agent",
        service_version=service_version,
    )
    otlp = build_otlp_http_exporter(endpoint=endpoint, api_key=api_key)
    exporter = ExportFilterSpanExporter(otlp)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(PipecatGenAIProcessor(context=context))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def _attach_processor_if_needed(provider: TracerProvider, context: ParlotContext) -> None:
    from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider

    from ._processor import PipecatGenAIProcessor

    if not isinstance(provider, SdkTracerProvider):
        return

    try:
        active = getattr(provider, "_active_span_processor", None)
        procs = getattr(active, "_span_processors", None) or getattr(
            active, "_processors", None
        )
        if procs and any(isinstance(p, PipecatGenAIProcessor) for p in procs):
            return
    except Exception:
        pass
    try:
        provider.add_span_processor(PipecatGenAIProcessor(context=context))
    except Exception:
        logger.debug("Could not attach PipecatGenAIProcessor", exc_info=True)


def _neutralize_pipecat_setup_tracing() -> None:
    """Prevent a later ``setup_tracing()`` from wiping our TracerProvider."""
    try:
        import pipecat.utils.tracing.setup as setup_mod
    except ImportError:
        return

    original = getattr(setup_mod, "setup_tracing", None)
    if original is None or getattr(original, "_parlot_wrapped", False):
        return

    def _wrapped(*args, **kwargs):
        logger.warning(
            "parlot: ignoring pipecat setup_tracing() — TracerProvider already "
            "configured by parlotize(); remove setup_tracing from your bot"
        )
        return True

    _wrapped._parlot_wrapped = True  # type: ignore[attr-defined]
    setup_mod.setup_tracing = _wrapped  # type: ignore[assignment]


def close_session(conversation_id: str, *, reason: str = "completed") -> None:
    """Public helper to close a Pipecat-owned session by conversation_id."""
    from ._session import close_session as _close

    _close(conversation_id, reason=reason)
