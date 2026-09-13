"""Auto-configuration for parlot-instrumentation-langgraph."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from opentelemetry.trace import TracerProvider

from parlot.core.context import ParlotContext

logger = logging.getLogger("parlot.instrumentation.langgraph")

_configured = False
_configured_agent_id: str | None = None
_configured_agent_version: str = ""
_parlot_context: ParlotContext | None = None


def parlotize(
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider: TracerProvider | None = None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    channel: Optional[str] = None,
    modality: Optional[str] = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> ParlotContext:
    """Parlotize LangGraph instrumentation and OTLP export.

    Registers a global LangChain callback handler (LangSmith-style) so
    ``invoke`` / ``ainvoke`` / ``astream`` emit GenAI spans without per-call
    callbacks. When LiveKit already owns the active session, contract spans
    are suppressed and GenAI ops nest under the current OTel context (LiveKit
    stamps channel/modality). For LangGraph-owned sessions, pass ``channel``
    (e.g. ``webchat``) and optionally ``modality`` so ingest does not assume
    voice.

    Shared kwargs (``endpoint``, ``api_key``, ``agent_id``, ``version``,
    ``capture_genai_content``, ``capture_logs``, ``log_level``,
    ``service_name``, ``tracer_provider``) match every adapter — see
    ``parlot.core.ParlotizeProtocol``.

    Args:
        endpoint: Shared — Parlot OTLP base URL (or ``PARLOT_ENDPOINT``).
        api_key: Shared — org API key (or ``PARLOT_API_KEY``).
        capture_genai_content: Shared — GenAI payload capture override.
            Precedence: this kwarg → Settings → Generative AI → on.
        service_name: Shared — OTel ``service.name`` (defaults to ``agent_id``
            or ``"langgraph-agent"``).
        tracer_provider: Shared — existing ``TracerProvider``. If LiveKit
            already initialized one in-process, this call adopts it.
        agent_id: Shared — canonical ``session.agent_id``.
        version: Shared — ``gen_ai.agent.version``. Pass ``version=`` to set it;
            otherwise ``\"unknown\"``.
        channel: Communication channel for standalone LangGraph sessions
            (e.g. ``"webchat"``, ``"slack"``, ``"sms"``). Defaults to
            ``"text"``. Ignored when LiveKit owns the session.
        modality: Session modality (``"text"``, ``"voice"``, or
            ``"multimodal"``). Defaults to ``"text"`` for standalone sessions.
        capture_logs: Shared — session log capture (bool or globs).
        log_level: Shared — minimum level for session log capture.

    Returns:
        The ``ParlotContext`` created for this process (or the prior one if
        already configured).
    """
    global _configured, _configured_agent_id, _configured_agent_version, _parlot_context
    if _configured:
        logger.debug("parlot-instrumentation.langgraph already configured — skipping")
        assert _parlot_context is not None
        return _parlot_context

    from parlot.core import base_parlotize
    from parlot.core.genai_content_capture import should_capture_genai_content
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    _configured_agent_id = agent_id.strip() if agent_id else None
    _configured_agent_version = (version or "").strip() or "unknown"

    res = base_parlotize(
        endpoint=endpoint,
        api_key=api_key,
        capture_genai_content=capture_genai_content,
        tracer_provider=tracer_provider,
        agent_id=agent_id,
        version=_configured_agent_version,
        capture_logs=capture_logs,
        log_level=log_level,
    )
    _parlot_context = res.context

    runtime = res.context.runtime
    capture = should_capture_genai_content(
        _configured_agent_id or "",
        capture_genai_content_config=res.capture_genai_content,
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
    from ._hooks import install_parlotize_hook
    from ._session import set_channel_modality, set_identity, set_tracer

    set_identity(_configured_agent_id or "", _configured_agent_version)
    set_channel_modality(channel=channel or "", modality=modality or "")
    set_tracer(tracer)
    handler = ParlotLangGraphCallbackHandler(tracer, capture_genai_content=capture)
    install_parlotize_hook(handler)

    _configured = True
    logger.debug(
        "parlot-instrumentation.langgraph configured (endpoint=%s)", res.endpoint
    )
    return res.context


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
    """Public helper to close a LangGraph-owned session by thread_id.

    Emits ``parlot.session.close`` with accumulated usage and turn counts.
    Optional — sessions are also flushed on process exit.

    Args:
        thread_id: LangGraph thread id from
            ``config={"configurable": {"thread_id": "..."}}``.
        reason: Close reason stamped on ``session.close_reason``. Defaults to
            ``"completed"``.
    """
    from ._session import close_session as _close

    _close(thread_id, reason=reason)
