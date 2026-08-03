"""Auto-configuration helpers for parlot-instrumentation-livekit."""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from typing import Any, Optional

logger = logging.getLogger("parlot.instrumentation.livekit")

_configured = False
_auto_escalate_sip = False
_escalation_metadata_match: dict[str, str] | None = None
_configured_agent_id: str | None = None
_configured_agent_version: str = ""
_configured_record: bool | list[str] | None = None


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
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_content: Optional[bool] = None,
    service_name: Optional[str] = None,
    tracer_provider=None,
    auto_escalate_sip: bool = False,
    escalation_metadata_match: dict[str, str] | None = None,
    agent_id: Optional[str] = None,
    version: Optional[str] = None,
    record: bool | list[str] | None = None,
) -> None:
    """Configure Parlot LiveKit instrumentation and OTLP export.

    Deployment version (``gen_ai.agent.version``) resolves once at configure time:
    ``version=`` kwarg → ``__main__.__version__`` / ``VERSION`` →
    ``PARLOT_AGENT_VERSION`` → local git SHA (dev only).

    Recording policy precedence: job metadata ``record`` >
    ``record=`` here > Settings → Recording (telemetry bootstrap).
    """
    global _configured, _auto_escalate_sip, _escalation_metadata_match
    global _configured_agent_id, _configured_agent_version, _configured_record
    if _configured:
        logger.debug("parlot-instrumentation.livekit already configured — skipping")
        return

    if _is_livekit_dev_watch_parent():
        logger.debug(
            "Skipping parlot-instrumentation.livekit configure in LiveKit dev "
            "watcher parent (worker child will configure)"
        )
        return

    _auto_escalate_sip = auto_escalate_sip
    _escalation_metadata_match = (
        dict(escalation_metadata_match) if escalation_metadata_match else None
    )
    _configured_agent_id = agent_id.strip() if agent_id else None
    if isinstance(record, list):
        _configured_record = [str(item).strip() for item in record if str(item).strip()]
    else:
        _configured_record = record

    from ._agent_version import resolve_agent_version

    _configured_agent_version = resolve_agent_version(version)

    _configure_parlot_logging()

    from parlot.core.diagnostics import init_diagnostics
    from parlot.core.provider import (
        adopt_existing_tracer_provider,
        resolve_api_key,
        resolve_capture_content,
        resolve_endpoint,
    )

    resolved_endpoint = resolve_endpoint(endpoint)
    resolved_api_key = resolve_api_key(api_key)
    capture_content = resolve_capture_content(capture_content)

    init_diagnostics(endpoint=resolved_endpoint, api_key=resolved_api_key)

    if tracer_provider is None:
        tracer_provider = adopt_existing_tracer_provider()
    if tracer_provider is None:
        tracer_provider = _build_provider(
            endpoint=resolved_endpoint,
            api_key=resolved_api_key,
            capture_content=capture_content,
            service_name=service_name,
            service_version=_configured_agent_version or None,
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
            logger.error(
                "parlot: telemetry bootstrap failed status=%s",
                resp.status_code,
            )
            return
        webhook_confirmation = apply_bootstrap_payload(endpoint, api_key, resp.json())
        if webhook_confirmation:
            logger.debug(
                "parlot: telemetry bootstrap cached (egress webhook confirmation enabled)"
            )
        else:
            logger.debug(
                "parlot: telemetry bootstrap cached "
                "(recording can still run; configure LiveKit integration for "
                "faster audio confirmation via webhooks)"
            )
    except Exception:
        logger.exception("parlot: telemetry bootstrap request failed")


def _build_provider(
    endpoint: str,
    api_key: str,
    capture_content: bool,
    service_name: Optional[str],
    service_version: Optional[str] = None,
):
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from parlot.core.processor import assert_sync_span_processors
    from parlot.core.provider import build_otlp_http_exporter, build_resource
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    from parlot.core.export import ExportFilterSpanExporter

    from ._export import QuietOTLPSpanExporter
    from ._export_filter import EnrichingExportSpanExporter
    from ._export_sanitize import SanitizeVendorAttrsSpanExporter
    from ._metrics import ParlotMetricsRecorder, build_meter_provider
    from ._processor import LiveKitGenAIProcessor
    from ._session import set_span_context_attach_enabled
    from ._turn_trace_export import TurnTraceRemappingExporter

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    resource = build_resource(
        service_name=service_name,
        service_version=service_version,
    )
    trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
    otlp_exporter = build_otlp_http_exporter(endpoint=endpoint, api_key=api_key)

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

    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    attach_ok = assert_sync_span_processors(provider)
    set_span_context_attach_enabled(attach_ok)

    meter_provider = build_meter_provider(endpoint, headers, resource)
    # Parlot metrics use a dedicated MeterProvider — do not call
    # otel_metrics.set_meter_provider() so LiveKit's lk.agents.usage.* counters
    # stay on the process default and are not exported to Parlot's pipeline.
    processor.set_tracer(
        provider.get_tracer(
            "parlot.instrumentation.livekit",
            resolve_parlot_sdk_version() or None,
        )
    )
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

    _parlot_connect._parlot_connect_patched = True
    JobContext.connect = _parlot_connect
    logger.debug("Patched JobContext.connect for room_sid + egress")


def _is_sip_participant(participant: Any) -> bool:
    kind = getattr(participant, "kind", None)
    if kind is None:
        return False
    try:
        from livekit.rtc import ParticipantKind

        return kind == ParticipantKind.SIP
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
