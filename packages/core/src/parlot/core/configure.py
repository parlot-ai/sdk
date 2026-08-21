"""Shared ``configure()`` keyword surface and base configuration helper.

All adapter ``configure()`` entrypoints are keyword-only so the shape can
evolve without breaking positional call sites.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger("parlot.core.configure")


@runtime_checkable
class ConfigureProtocol(Protocol):
    """Common kwargs every adapter ``configure()`` must accept.

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
        tracer_provider: Any = None,
        agent_id: Optional[str] = None,
        version: Optional[str] = None,
        capture_logs: bool | list[str] | None = None,
        log_level: Optional[str] = None,
        **kwargs: Any,
    ) -> None: ...


@dataclass
class BaseConfigureResult:
    """Resolved context from ``base_configure`` for framework adapters."""

    endpoint: str
    api_key: str
    tracer_provider: Any
    agent_id: Optional[str]
    agent_version: str
    capture_genai_content: Optional[bool]
    capture_logs: bool | list[str] | None
    log_level: Optional[str]


def configure_parlot_logging() -> None:
    level_name = os.getenv("PARLOT_DEBUG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    if not logging.root.handlers:
        logging.basicConfig(level=level)


def base_configure(
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    tracer_provider: Any = None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> BaseConfigureResult:
    """Execute shared telemetry configuration common across all adapters.

    Resolves endpoint, API key, diagnostics, session log collectors,
    and remote bootstrap cache.
    """
    from parlot.core.bootstrap import fetch_telemetry_bootstrap
    from parlot.core.diagnostics import init_diagnostics
    from parlot.core.provider import (
        adopt_existing_tracer_provider,
        resolve_api_key,
        resolve_capture_genai_content,
        resolve_endpoint,
    )
    from parlot.core.session_logs import (
        init_session_logs,
        set_capture_logs_configure,
    )

    configure_parlot_logging()

    resolved_agent_id = agent_id.strip() if agent_id else None
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

    init_diagnostics(endpoint=resolved_endpoint, api_key=resolved_api_key)
    set_capture_logs_configure(
        resolved_capture_logs,
        log_level=resolved_log_level,
    )
    init_session_logs(endpoint=resolved_endpoint, api_key=resolved_api_key)

    if resolved_api_key:
        fetch_telemetry_bootstrap(resolved_endpoint, resolved_api_key)

    if tracer_provider is None:
        tracer_provider = adopt_existing_tracer_provider()

    return BaseConfigureResult(
        endpoint=resolved_endpoint,
        api_key=resolved_api_key,
        tracer_provider=tracer_provider,
        agent_id=resolved_agent_id,
        agent_version=resolved_version,
        capture_genai_content=resolved_capture_content,
        capture_logs=resolved_capture_logs,
        log_level=resolved_log_level,
    )
