"""parlot-core: shared semantic conventions, base processor, and utilities."""

from .attrs import *  # noqa: F401, F403 — re-export all attribute constants
from .context import ParlotContext
from .escalation import human_escalation, record_human_rep
from .metadata import set_session_attribute, set_session_metadata
from .platform_refs import add_platform_ref, stamp_framework_refs, stamp_platform_refs
from .processor import ParlotBaseProcessor, assert_sync_span_processors
from .provider import (
    adopt_existing_tracer_provider,
    attach_span_processor_if_absent,
    build_filtered_tracer_provider,
    build_otlp_http_exporter,
    build_parlot_client_headers,
    build_resource,
    build_tracer_provider,
    resolve_api_key,
    resolve_capture_genai_content,
    resolve_endpoint,
    resolve_service_name,
    try_set_global_tracer_provider,
    HEADER_SDK_NAME,
    HEADER_SDK_VERSION,
    HEADER_INGESTION_VERSION,
    INGESTION_PROTOCOL_VERSION,
)
from .bootstrap import fetch_telemetry_bootstrap
from .parlotize import (
    BaseParlotizeResult,
    ParlotizeProtocol,
    base_parlotize,
    configure_parlot_logging,
    log_parlotize_ready,
    normalize_glob_or_bool,
)
from .genai_content_capture import should_capture_genai_content
from .export import ExportFilterSpanExporter
from .intent import derive_intent
from .logs_capture import should_capture_logs
from .recording import should_record
from .recording_source import RecordingSource, stamp_external_recording
from .recording_stamp import (
    stamp_recording_disabled,
    stamp_recording_error,
    stamp_recording_started,
    stamp_recording_uploaded,
)
from .recording_timeline import (
    media_segments_from_speech,
    set_recording_anchor_wall_ms,
    speech_wall_ms_from_span,
)
from .recording_upload import (
    complete_recording,
    fetch_upload_grant,
    put_bytes_to_presigned_url,
)
from .metrics import (
    LONG_LIVED_METRICS_EXPORT_INTERVAL_MS,
    ParlotMetricsRecorder,
    QuietOTLPMetricExporter,
    UsageMetricsRecorder,
    build_parlot_meter_provider,
)
from .runtime import ParlotRuntimeContext, runtime_from_bootstrap
from .sdk_version import resolve_parlot_sdk_version, stamp_session_sdk_version
from .session import (
    SessionState,
    clear_active_session,
    get_active_session,
    get_active_session_span,
    session_owned,
    set_active_session,
)
from .session_lifecycle import (
    DEFAULT_CLOSE_FLUSH_ATTEMPT_TIMEOUT_MS,
    DEFAULT_CLOSE_FLUSH_BACKOFFS_S,
    DEFAULT_CLOSE_FLUSH_BUDGET_S,
    emit_parlot_session_close,
    end_session_span_ok,
    force_flush_tracer_provider,
    force_flush_with_budget,
    start_parlot_session_span,
)
from .session_logs import SessionLogsCollector
from .session_registry import ConversationSessionRegistry
from .span_rename import apply_genai_span_rename, remap_native_span_name
from .topology import SessionTopology
from .turn_emit import emit_parlot_turn_root, stamp_turn_utterance_text

__all__ = [
    "BaseParlotizeResult",
    "ConversationSessionRegistry",
    "DEFAULT_CLOSE_FLUSH_ATTEMPT_TIMEOUT_MS",
    "DEFAULT_CLOSE_FLUSH_BACKOFFS_S",
    "DEFAULT_CLOSE_FLUSH_BUDGET_S",
    "ParlotizeProtocol",
    "ParlotContext",
    "ParlotRuntimeContext",
    "SessionLogsCollector",
    "apply_genai_span_rename",
    "attach_span_processor_if_absent",
    "base_parlotize",
    "build_filtered_tracer_provider",
    "configure_parlot_logging",
    "emit_parlot_session_close",
    "emit_parlot_turn_root",
    "end_session_span_ok",
    "ExportFilterSpanExporter",
    "force_flush_tracer_provider",
    "force_flush_with_budget",
    "LONG_LIVED_METRICS_EXPORT_INTERVAL_MS",
    "log_parlotize_ready",
    "normalize_glob_or_bool",
    "ParlotBaseProcessor",
    "ParlotMetricsRecorder",
    "QuietOTLPMetricExporter",
    "UsageMetricsRecorder",
    "assert_sync_span_processors",
    "SessionState",
    "SessionTopology",
    "add_platform_ref",
    "adopt_existing_tracer_provider",
    "build_otlp_http_exporter",
    "build_parlot_client_headers",
    "build_parlot_meter_provider",
    "build_resource",
    "build_tracer_provider",
    "HEADER_SDK_NAME",
    "HEADER_SDK_VERSION",
    "HEADER_INGESTION_VERSION",
    "INGESTION_PROTOCOL_VERSION",
    "clear_active_session",
    "derive_intent",
    "fetch_telemetry_bootstrap",
    "get_active_session",
    "get_active_session_span",
    "human_escalation",
    "record_human_rep",
    "remap_native_span_name",
    "resolve_api_key",
    "resolve_capture_genai_content",
    "resolve_endpoint",
    "resolve_service_name",
    "resolve_parlot_sdk_version",
    "runtime_from_bootstrap",
    "session_owned",
    "set_active_session",
    "set_session_attribute",
    "set_session_metadata",
    "should_capture_genai_content",
    "should_record",
    "RecordingSource",
    "stamp_external_recording",
    "stamp_recording_disabled",
    "stamp_recording_error",
    "stamp_recording_started",
    "stamp_recording_uploaded",
    "set_recording_anchor_wall_ms",
    "media_segments_from_speech",
    "speech_wall_ms_from_span",
    "fetch_upload_grant",
    "complete_recording",
    "put_bytes_to_presigned_url",
    "should_capture_logs",
    "stamp_framework_refs",
    "stamp_platform_refs",
    "stamp_session_sdk_version",
    "stamp_turn_utterance_text",
    "start_parlot_session_span",
    "try_set_global_tracer_provider",
]
