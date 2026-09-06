"""Auto-configuration helpers for parlot-instrumentation-livekit."""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from opentelemetry.trace import TracerProvider

from parlot.core.context import ParlotContext

logger = logging.getLogger("parlot.instrumentation.livekit")

_configured = False
_auto_escalate_sip = False
_escalation_metadata_match: dict[str, str] | None = None
_configured_agent_id: str | None = None
_configured_agent_version: str = ""
_configured_record: bool | list[str] | None = None
_configured_capture_genai_content: bool | None = None
_configured_capture_logs: bool | list[str] | None = None
_configured_log_level: str | None = None
_parlot_context: ParlotContext | None = None


def _is_livekit_dev_watch_parent() -> bool:
    """True when this process is LiveKit's dev-mode file-watcher parent.

    ``lk agent dev`` maps to ``python -m livekit.agents start --dev`` (reload
    on by default). That parent imports the agent only to watch files, then
    spawns a child worker that re-imports and runs jobs. Instrumentation
    belongs in the child.

    The spawned child inherits ``sys.argv`` (including ``--dev`` / legacy
    ``dev``) and, while ``agent.py`` is re-imported during
    ``multiprocessing`` spawn setup, ``parent_process()`` is still ``None``.
    Use the process name instead: only the top-level watcher is
    ``MainProcess``.
    """
    if multiprocessing.current_process().name != "MainProcess":
        return False

    argv = sys.argv
    # New CLI: ``start --dev``. Legacy rich CLI: ``… dev`` subcommand.
    if "--dev" not in argv and "dev" not in argv:
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
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_genai_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider: TracerProvider | None = None,
    auto_escalate_sip: bool = False,
    escalation_metadata_match: dict[str, str] | None = None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    record: bool | list[str] | None = None,
    capture_logs: bool | list[str] | None = None,
    log_level: Optional[str] = None,
) -> ParlotContext:
    """Configure Parlot LiveKit instrumentation and OTLP export.

    Call before constructing ``AgentSession``. Builds a ``TracerProvider`` with
    an OTLP exporter, registers it with ``livekit.agents.telemetry``, fetches
    telemetry bootstrap when ``PARLOT_API_KEY`` is set, patches
    ``JobContext.connect`` / ``AgentSession.__init__``, and installs session
    event hooks.

    Shared kwargs (``endpoint``, ``api_key``, ``agent_id``, ``version``,
    ``capture_genai_content``, ``capture_logs``, ``log_level``,
    ``service_name``, ``tracer_provider``) match every adapter — see
    ``parlot.core.ConfigureProtocol``.

    Under LiveKit ``dev`` / job workers, ``__main__`` is often LiveKit's IPC
    entrypoint, not your agent file — prefer explicit ``agent_id=`` /
    ``version=`` (or ``PARLOT_AGENT_VERSION``) over relying on
    ``__main__.__version__``.

    Args:
        endpoint: Shared — Parlot OTLP base URL (or ``PARLOT_ENDPOINT``).
        api_key: Shared — org API key (or ``PARLOT_API_KEY``).
        capture_genai_content: Shared — GenAI payload capture override.
            Precedence: job metadata → this kwarg → Settings → Generative AI → on.
        service_name: Shared — OTel ``service.name`` (defaults to ``agent_id``
            or ``"unknown"``).
        tracer_provider: Shared — existing ``TracerProvider``, or build one with
            Parlot's OTLP exporter and ``LiveKitGenAIProcessor``.
        auto_escalate_sip: When ``True``, mark the session escalated when a SIP
            participant joins the room.
        escalation_metadata_match: Participant metadata key/value pairs that
            classify joining participants as human representatives.
        agent_id: Shared — canonical ``session.agent_id``. If omitted, falls
            back to LiveKit ``WorkerOptions.agent_name`` / job ``agent_name`` or
            ``PARLOT_AGENT_ID``.
        version: Shared — ``gen_ai.agent.version``. Precedence: this kwarg →
            ``__main__.__version__`` / ``VERSION`` → ``PARLOT_AGENT_VERSION`` →
            local git SHA (dev only).
        record: Audio recording policy. Boolean or agent-id glob patterns
            (e.g. ``["support-*", "billing"]``). Precedence: LiveKit job
            metadata ``record`` → this kwarg → Settings → Recording.
        capture_logs: Shared — session log capture (bool or globs). Precedence:
            job metadata → this kwarg → Settings → Logs → on.
        log_level: Shared — minimum level for session log capture.

    Returns:
        The ``ParlotContext`` created for this process (or the prior one if
        already configured).
    """
    global _configured, _auto_escalate_sip, _escalation_metadata_match
    global _configured_agent_id, _configured_agent_version, _configured_record
    global _configured_capture_genai_content, _configured_capture_logs, _configured_log_level
    global _parlot_context
    if _configured:
        logger.debug("parlot-instrumentation.livekit already configured — skipping")
        assert _parlot_context is not None
        return _parlot_context

    if _is_livekit_dev_watch_parent():
        logger.debug(
            "Skipping parlot-instrumentation.livekit configure in LiveKit dev "
            "watcher parent (worker child will configure)"
        )
        return ParlotContext()

    _auto_escalate_sip = auto_escalate_sip
    _escalation_metadata_match = (
        dict(escalation_metadata_match) if escalation_metadata_match else None
    )
    _configured_agent_id = agent_id.strip() if agent_id else None
    if isinstance(record, list):
        _configured_record = [str(item).strip() for item in record if str(item).strip()]
    else:
        _configured_record = record
    from parlot.core.provider import resolve_capture_genai_content

    _configured_capture_genai_content = resolve_capture_genai_content(capture_genai_content)
    if isinstance(capture_logs, list):
        _configured_capture_logs = [
            str(item).strip() for item in capture_logs if str(item).strip()
        ]
    else:
        _configured_capture_logs = capture_logs
    _configured_log_level = log_level.strip().upper() if log_level else None

    from ._agent_version import resolve_agent_version
    _configured_agent_version = resolve_agent_version(version)

    from parlot.core import base_configure

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
    _parlot_context = res.context

    from ._recording_guard import (
        current_job_capture_logs_metadata,
        livekit_session_log_fields,
        recording_agent_id_from_ctx,
    )

    def _agent_id_resolver() -> str:
        try:
            from livekit.agents.job import get_job_context

            ctx = get_job_context()
            if ctx is not None:
                return recording_agent_id_from_ctx(ctx)
        except Exception:
            pass
        return _configured_agent_id or ""

    res.context.session_logs.set_resolvers(
        session_resolver=livekit_session_log_fields,
        agent_id_resolver=_agent_id_resolver,
        metadata_resolver=current_job_capture_logs_metadata,
    )

    tracer_provider = res.tracer_provider
    if tracer_provider is None:
        tracer_provider = _build_provider(
            endpoint=res.endpoint,
            api_key=res.api_key,
            service_name=service_name,
            service_version=_configured_agent_version or None,
            context=res.context,
        )

    from parlot.core.processor import assert_sync_span_processors

    from ._session import set_span_context_attach_enabled

    attach_ok = assert_sync_span_processors(tracer_provider)
    set_span_context_attach_enabled(attach_ok)

    _register_with_livekit(tracer_provider)
    _patch_agent_session_with_tracer(tracer_provider)
    _patch_job_context_connect()
    _install_telemetry_compare()

    _configured = True
    logger.debug("parlot-instrumentation.livekit configured (endpoint=%s)", res.endpoint)
    return res.context


def _build_provider(
    endpoint: str,
    api_key: str,
    service_name: Optional[str],
    service_version: Optional[str] = None,
    *,
    context: ParlotContext,
):
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from parlot.core.processor import assert_sync_span_processors
    from parlot.core.provider import build_otlp_http_exporter, build_resource
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    from parlot.core.export import ExportFilterSpanExporter

    from ._export import QuietOTLPSpanExporter
    from ._export_filter import EnrichingExportSpanExporter
    from ._export_sanitize import SanitizeVendorAttrsSpanExporter
    from parlot.core.provider import build_parlot_client_headers
    from ._metrics import ParlotMetricsRecorder, build_meter_provider
    from ._processor import LiveKitGenAIProcessor
    from ._session import set_span_context_attach_enabled
    from ._turn_trace_export import TurnTraceRemappingExporter

    headers = build_parlot_client_headers(api_key)

    resource = build_resource(
        service_name=service_name,
        service_version=service_version,
    )
    trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
    otlp_exporter = build_otlp_http_exporter(endpoint=endpoint, api_key=api_key)

    processor = LiveKitGenAIProcessor(context=context)

    # Rename (enrich) must run on real spans *before* sanitize wraps them and
    # *before* the GenAI/voice allowlist filter — otherwise native names like
    # llm_node / tts_node are dropped and never remapped.
    remapping_exporter = TurnTraceRemappingExporter(otlp_exporter, processor)
    filtered_exporter = ExportFilterSpanExporter(remapping_exporter)
    sanitized_exporter = SanitizeVendorAttrsSpanExporter(filtered_exporter)
    enriching_exporter = EnrichingExportSpanExporter(sanitized_exporter, processor)
    exporter = QuietOTLPSpanExporter(
        enriching_exporter,
        endpoint_label=trace_endpoint,
    )

    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    attach_ok = assert_sync_span_processors(provider)
    set_span_context_attach_enabled(attach_ok)

    meter_provider = build_meter_provider(
        endpoint, headers, resource
    )
    # Parlot metrics use a dedicated MeterProvider — do not call
    # otel_metrics.set_meter_provider() so LiveKit's lk.agents.usage.* counters
    # stay on the process default and are not exported to Parlot's pipeline.
    processor.set_tracer(
        provider.get_tracer(
            "parlot.instrumentation.livekit",
            resolve_parlot_sdk_version() or None,
        )
    )
    processor.set_metrics(ParlotMetricsRecorder(meter_provider, context=context))

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
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    tracer = provider.get_tracer(
        "parlot.instrumentation.livekit",
        resolve_parlot_sdk_version() or None,
    )

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

        _install_participant_escalation_hooks(self)

        if get_job_bootstrap() is None:
            return
        await _run_post_bootstrap_connect(self)

    setattr(_parlot_connect, "_parlot_connect_patched", True)
    setattr(JobContext, "connect", _parlot_connect)
    logger.debug("Patched JobContext.connect for room_sid + egress")


def _is_sip_participant(participant: Any) -> bool:
    kind = getattr(participant, "kind", None)
    if kind is None:
        return False
    try:
        from livekit.rtc import ParticipantKind

        return kind == ParticipantKind.PARTICIPANT_KIND_SIP
    except (ImportError, AttributeError):
        kind_name = str(getattr(kind, "name", kind)).upper()
        return kind_name in ("SIP", "PARTICIPANT_KIND_SIP")


def _install_participant_escalation_hooks(job_ctx: Any) -> None:
    room = getattr(job_ctx, "room", None)
    if room is None:
        return

    if getattr(room, "_parlot_escalation_hooks_installed", False):
        return
    room._parlot_escalation_hooks_installed = True

    import json

    from parlot.core import record_human_rep
    from parlot.core.escalation import _pending_escalation_label

    def _on_participant_connected(participant: Any) -> None:
        identity = str(getattr(participant, "identity", "") or "").strip()
        if not identity:
            return

        pending_label = _pending_escalation_label.get()
        if pending_label is not None:
            record_human_rep(identity, label=pending_label)
            _pending_escalation_label.set(None)
            return

        display_name = str(getattr(participant, "name", "") or "").strip() or None

        if _auto_escalate_sip and _is_sip_participant(participant):
            record_human_rep(identity, label=display_name)
            return

        if _escalation_metadata_match:
            raw_metadata = getattr(participant, "metadata", "") or ""
            try:
                meta = json.loads(raw_metadata) if raw_metadata else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                meta = {}
            if all(meta.get(k) == v for k, v in _escalation_metadata_match.items()):
                record_human_rep(identity, label=display_name)

    room.on("participant_connected", _on_participant_connected)


def configured_agent_id() -> str:
    """Canonical deployment id from ``configure(agent_id=...)`` if set."""
    return _configured_agent_id or ""


def configured_agent_version() -> str:
    """Deployment version resolved at ``configure()`` time."""
    return _configured_agent_version


def configured_record() -> bool | list[str] | None:
    """Recording override from ``configure(record=...)`` if set."""
    return _configured_record


def configured_capture_genai_content() -> bool | None:
    """Content capture override from ``configure(capture_genai_content=...)`` if set."""
    return _configured_capture_genai_content


def configured_capture_logs() -> bool | list[str] | None:
    """Log capture override from ``configure(capture_logs=...)`` if set."""
    return _configured_capture_logs


def configured_log_level() -> str | None:
    """Log level override from ``configure(log_level=...)`` if set."""
    return _configured_log_level


def configured_context() -> ParlotContext | None:
    """``ParlotContext`` created by the last successful ``configure()``."""
    return _parlot_context


def set_configured_context(context: ParlotContext | None) -> None:
    """Test helper to install or clear the configured ``ParlotContext``."""
    global _parlot_context
    _parlot_context = context

