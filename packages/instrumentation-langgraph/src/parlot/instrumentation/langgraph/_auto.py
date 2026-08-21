"""Auto-configuration for parlot-instrumentation-langgraph."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("parlot.instrumentation.langgraph")

_configured = False
_configured_agent_id: str | None = None
_configured_agent_version: str = ""


def configure(
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider=None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    channel: Optional[str] = None,
    modality: Optional[str] = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> None:
    """Configure Parlot LangGraph instrumentation and OTLP export.

    Registers a global LangChain callback handler (LangSmith-style) so
    ``invoke`` / ``ainvoke`` / ``astream`` emit GenAI spans without per-call
    callbacks. When LiveKit already owns the active session, contract spans
    are suppressed and GenAI ops nest under the current OTel context (LiveKit
    stamps channel/modality). For LangGraph-owned sessions, pass ``channel``
    (e.g. ``webchat``) and optionally ``modality`` so ingest does not assume
    voice.
    """
    global _configured, _configured_agent_id, _configured_agent_version
    if _configured:
        logger.debug("parlot-instrumentation.langgraph already configured — skipping")
        return

    from parlot.core import base_configure
    from parlot.core.genai_content_capture import should_capture_genai_content
    from parlot.core.runtime import get_runtime
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    _configured_agent_id = agent_id.strip() if agent_id else None
    _configured_agent_version = (version or os.environ.get("PARLOT_AGENT_VERSION") or "").strip()

    res = base_configure(
        endpoint=endpoint,
        api_key=api_key,
        capture_genai_content=capture_genai_content,
        tracer_provider=tracer_provider,
        agent_id=agent_id,
        version=_configured_agent_version,
        capture_logs=capture_logs,
        log_level=log_level,
    )

    runtime = get_runtime()
    capture = should_capture_genai_content(
        _configured_agent_id or "",
        configure_capture_genai_content=res.capture_genai_content,
        bootstrap_globs=list(runtime.capture_genai_content_globs) if runtime else None,
        bootstrap_agents=runtime.capture_genai_content_agents_map() if runtime else None,
        bootstrap_present=bool(runtime and runtime.capture_genai_content_policy_present),
    )

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
            service_name=service_name,
            service_version=_configured_agent_version or None,
        )

    from opentelemetry import trace

    try:
        trace.set_tracer_provider(tracer_provider)
    except Exception:
        logger.debug("Could not set global tracer provider", exc_info=True)

    tracer = tracer_provider.get_tracer(
        "parlot.instrumentation.langgraph",
        resolve_parlot_sdk_version() or None,
    )

    from ._callbacks import ParlotLangGraphCallbackHandler
    from ._hooks import install_configure_hook
    from ._session import set_channel_modality, set_identity, set_tracer

    set_identity(_configured_agent_id or "", _configured_agent_version)
    set_channel_modality(channel=channel or "", modality=modality or "")
    set_tracer(tracer)
    handler = ParlotLangGraphCallbackHandler(tracer, capture_genai_content=capture)
    install_configure_hook(handler)

    _configured = True
    logger.debug(
        "parlot-instrumentation.langgraph configured (endpoint=%s)", resolved_endpoint
    )


def _build_provider(
    *,
    endpoint: str,
    api_key: str,
    service_name: Optional[str],
    service_version: Optional[str] = None,
):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from parlot.core.export import ExportFilterSpanExporter
    from parlot.core.provider import build_otlp_http_exporter, build_resource

    resource = build_resource(
        service_name=service_name or "langgraph-agent",
        service_version=service_version,
    )
    otlp = build_otlp_http_exporter(endpoint=endpoint, api_key=api_key)
    exporter = ExportFilterSpanExporter(otlp)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def close_session(thread_id: str, *, reason: str = "completed") -> None:
    """Public helper to close a LangGraph-owned session by thread_id."""
    from ._session import close_session as _close

    _close(thread_id, reason=reason)
