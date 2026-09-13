"""Shared ``parlotize()`` keyword surface and base configuration helper.

All adapter ``parlotize()`` entrypoints are keyword-only so the shape can
evolve without breaking positional call sites.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from opentelemetry.trace import TracerProvider

from parlot.core.context import ParlotContext

logger = logging.getLogger("parlot.core.parlotize")


@runtime_checkable
class ParlotizeProtocol(Protocol):
    """Common kwargs every adapter ``parlotize()`` must accept.

    Framework packages may add extra keyword-only parameters (e.g. LiveKit
    ``record=`` / ``auto_escalate_sip=``).
    """

    def __call__(
        self,
        *,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        capture_genai_content: Optional[bool] = None,
        service_name: Optional[str] = None,
        tracer_provider: TracerProvider | None = None,
        agent_id: Optional[str] = None,
        version: Optional[str] = None,
        capture_logs: bool | list[str] | None = None,
        log_level: Optional[str] = None,
        **kwargs: Any,
    ) -> ParlotContext:
        """Shared keyword surface for every adapter ``parlotize()``.

        Args:
            endpoint: Parlot OTLP collector base URL (e.g.
                ``https://ingest.parlot.ai``). Spans export to
                ``{endpoint}/v1/traces``. If omitted, reads ``PARLOT_ENDPOINT``.
            api_key: Org-scoped API key minted in Parlot **Settings → API Keys**.
                If omitted, reads ``PARLOT_API_KEY``. Required for remote telemetry
                bootstrap and recording grants.
            capture_genai_content: Process-wide override for LLM message bodies and
                tool input/output payloads. If ``False``, payloads are omitted while
                preserving span durations, tokens, and turn text. Precedence: job
                metadata → this kwarg → Settings → Generative AI (default: on).
            service_name: OpenTelemetry resource ``service.name``. Defaults to
                ``agent_id`` or a framework-specific fallback.
            tracer_provider: Existing OpenTelemetry ``TracerProvider`` to adopt. If
                omitted, adapters build one with Parlot's OTLP exporter (or adopt an
                already-registered provider when another adapter configured first).
            agent_id: Canonical deployment identity stamped on ``session.agent_id``.
                If omitted, adapters may derive from framework config or
                ``PARLOT_AGENT_ID``.
            version: Deployment version stamped on ``gen_ai.agent.version``.
                Precedence: this kwarg → ``__main__.__version__`` / ``VERSION`` →
                ``PARLOT_AGENT_VERSION`` → local git short SHA (dev only).
            capture_logs: Intercept Python ``logging`` during active sessions and
                stream to the session Logs tab. Boolean or agent-id glob patterns.
                Precedence: job metadata → this kwarg → Settings → Logs (default: on).
            log_level: Minimum level for session log capture (e.g. ``"INFO"``,
                ``"WARNING"``). Defaults to ``"INFO"``.
            **kwargs: Framework-specific options (ignored by the shared surface).
        """
        ...


@dataclass
class BaseParlotizeResult:
    """Resolved context from ``base_parlotize`` for framework adapters."""

    context: ParlotContext
    endpoint: str
    api_key: str
    tracer_provider: Any
    agent_id: Optional[str]
    agent_version: str
    capture_genai_content: Optional[bool]
    capture_logs: bool | list[str] | None
    log_level: Optional[str]


def configure_parlot_logging() -> None:
    """Configure root logging from ``PARLOT_DEBUG_LEVEL`` when no handlers exist."""
    level_name = os.getenv("PARLOT_DEBUG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not logging.root.handlers:
        logging.basicConfig(level=level)


def base_parlotize(
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    tracer_provider: TracerProvider | None = None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> BaseParlotizeResult:
    """Execute shared telemetry configuration common across all adapters.

    Creates a ``ParlotContext``, initializes the session log
    collector, and fetches remote bootstrap into ``context.runtime``.

    See ``ParlotizeProtocol`` for the shared keyword surface.

    Args:
        endpoint: Parlot OTLP collector base URL. If omitted, reads
            ``PARLOT_ENDPOINT``.
        api_key: Org-scoped API key. If omitted, reads ``PARLOT_API_KEY``.
        capture_genai_content: Process-wide GenAI content capture override.
        tracer_provider: Existing ``TracerProvider`` to adopt, if any.
        agent_id: Canonical deployment identity for ``session.agent_id``.
        version: Deployment version for ``gen_ai.agent.version``.
        capture_logs: Session log capture policy (bool or agent-id globs).
        log_level: Minimum level for session log capture.

    Returns:
        Resolved endpoint, credentials, provider, and capture settings for the
        calling adapter.
    """
    from parlot.core.bootstrap import fetch_telemetry_bootstrap
    from parlot.core.context import ParlotContext
    from parlot.core.provider import (
        adopt_existing_tracer_provider,
        resolve_api_key,
        resolve_capture_genai_content,
        resolve_endpoint,
    )

    configure_parlot_logging()

    resolved_agent_id = (
        agent_id.strip()
        if agent_id
        else (os.environ.get("PARLOT_AGENT_ID") or "").strip() or None
    )
    resolved_version = (version or os.environ.get("PARLOT_AGENT_VERSION") or "").strip()
    resolved_endpoint = resolve_endpoint(endpoint)
    resolved_api_key = resolve_api_key(api_key)
    resolved_capture_content = resolve_capture_genai_content(capture_genai_content)

    if isinstance(capture_logs, list):
        resolved_capture_logs: bool | list[str] | None = [
            str(item).strip() for item in capture_logs if str(item).strip()
        ]
    else:
        resolved_capture_logs = capture_logs

    resolved_log_level = log_level.strip().upper() if log_level else None

    context = ParlotContext()
    context.session_logs.set_capture_logs_config(
        resolved_capture_logs,
        log_level=resolved_log_level,
    )
    context.session_logs.init(endpoint=resolved_endpoint, api_key=resolved_api_key)

    if resolved_api_key:
        fetch_telemetry_bootstrap(resolved_endpoint, resolved_api_key, context)

    if tracer_provider is None:
        tracer_provider = adopt_existing_tracer_provider()

    return BaseParlotizeResult(
        context=context,
        endpoint=resolved_endpoint,
        api_key=resolved_api_key,
        tracer_provider=tracer_provider,
        agent_id=resolved_agent_id,
        agent_version=resolved_version,
        capture_genai_content=resolved_capture_content,
        capture_logs=resolved_capture_logs,
        log_level=resolved_log_level,
    )
