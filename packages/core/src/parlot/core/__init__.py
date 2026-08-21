"""parlot-core: shared semantic conventions, base processor, and utilities."""

from .attrs import *  # noqa: F401, F403 — re-export all attribute constants
from .diagnostics import (
    diagnostics_enabled,
    init_diagnostics,
    record_diagnostic,
    shutdown_diagnostics,
)
from .escalation import human_escalation, record_human_rep
from .metadata import set_session_attribute, set_session_metadata
from .platform_refs import add_platform_ref, stamp_platform_refs
from .processor import ParlotBaseProcessor, assert_sync_span_processors
from .provider import (
    adopt_existing_tracer_provider,
    build_otlp_http_exporter,
    build_resource,
    build_tracer_provider,
    resolve_api_key,
    resolve_capture_genai_content,
    resolve_endpoint,
)
from .bootstrap import fetch_telemetry_bootstrap
from .configure import BaseConfigureResult, ConfigureProtocol, base_configure, configure_parlot_logging
from .genai_content_capture import should_capture_genai_content
from .export import ExportFilterSpanExporter
from .intent import derive_intent
from .logs_capture import should_capture_logs
from .sdk_version import resolve_parlot_sdk_version, stamp_session_sdk_version
from .session import (
    SessionState,
    clear_active_session,
    get_active_session,
    get_active_session_span,
    session_owned,
    set_active_session,
)
from .session_logs import init_session_logs, shutdown_session_logs
from .topology import SessionTopology

__all__ = [
    "BaseConfigureResult",
    "ConfigureProtocol",
    "base_configure",
    "configure_parlot_logging",
    "ExportFilterSpanExporter",
    "ParlotBaseProcessor",
    "assert_sync_span_processors",
    "SessionState",
    "SessionTopology",
    "add_platform_ref",
    "adopt_existing_tracer_provider",
    "build_otlp_http_exporter",
    "build_resource",
    "build_tracer_provider",
    "clear_active_session",
    "derive_intent",
    "diagnostics_enabled",
    "fetch_telemetry_bootstrap",
    "get_active_session",
    "get_active_session_span",
    "human_escalation",
    "init_diagnostics",
    "init_session_logs",
    "record_diagnostic",
    "record_human_rep",
    "resolve_api_key",
    "resolve_capture_genai_content",
    "resolve_endpoint",
    "resolve_parlot_sdk_version",
    "session_owned",
    "set_active_session",
    "set_session_attribute",
    "set_session_metadata",
    "should_capture_genai_content",
    "should_capture_logs",
    "shutdown_diagnostics",
    "shutdown_session_logs",
    "stamp_platform_refs",
    "stamp_session_sdk_version",
]
