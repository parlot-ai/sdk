"""Auto-configuration helpers for parlot-instrumentation-pipecat."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from opentelemetry.trace import TracerProvider

from parlot.core.context import ParlotContext

logger = logging.getLogger("parlot.instrumentation.pipecat")

_configured = False
_configured_agent_id: str | None = None
_configured_agent_version: str = ""
_configured_record: bool | list[str] | None = None
_parlot_context: ParlotContext | None = None
_active_recorders: list[Any] = []


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
    record: bool | list[str] | None = None,
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
        record: Audio recording policy. Boolean or agent-id glob patterns.
            When enabled, place ``ParlotRecordingProcessor`` after
            ``transport.output()`` (WAV segments by default).

    Returns:
        The ``ParlotContext`` for this process.
    """
    global _configured, _configured_agent_id, _configured_agent_version
    global _configured_record, _parlot_context
    if _configured:
        logger.debug("parlot-instrumentation.pipecat already configured — skipping")
        assert _parlot_context is not None
        return _parlot_context

    from parlot.core import base_parlotize
    from parlot.core.parlotize import normalize_glob_or_bool
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    _configured_agent_version = (version or "").strip() or "unknown"
    _configured_record = normalize_glob_or_bool(record)

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

    from parlot.core.provider import try_set_global_tracer_provider
    from parlot.core.parlotize import log_parlotize_ready

    try_set_global_tracer_provider(tracer_provider)

    from ._hooks import (
        install_aggregator_turn_hooks,
        install_pipeline_worker_hooks,
        install_tool_call_hooks,
    )
    from ._session import set_identity, set_tracer

    set_identity(_configured_agent_id, _configured_agent_version)
    set_tracer(
        tracer_provider.get_tracer(
            "parlot.instrumentation.pipecat",
            resolve_parlot_sdk_version() or None,
        )
    )
    _wire_session_logs(res.context, _configured_agent_id)
    install_pipeline_worker_hooks()
    install_tool_call_hooks()
    install_aggregator_turn_hooks()
    _neutralize_pipecat_setup_tracing()

    _configured = True
    log_parlotize_ready(
        "pipecat",
        agent_id=res.agent_id,
        endpoint=res.endpoint or "",
        api_key=res.api_key or "",
        log=logger,
    )
    return res.context


def _wire_session_logs(context: ParlotContext, agent_id: str) -> None:
    """Bind active-session fields + forward loguru into session log capture."""
    from ._session import any_open_session

    def _session_resolver() -> dict | None:
        # Prefer ContextVar; fall back to the process-global open session map.
        # Pipeline worker vs uvicorn threads do not share ContextVars.
        state = any_open_session()
        if state is None or not getattr(state, "session_id", None):
            return None
        return {
            "session_id": state.session_id,
            "conversation_id": getattr(state, "conversation_id", "") or state.session_id,
            "turn_index": int(getattr(state, "turn_count", 0) or 0),
        }

    context.session_logs.set_resolvers(
        session_resolver=_session_resolver,
        agent_id_resolver=lambda: agent_id,
    )
    _install_loguru_session_sink(context, agent_id)


def _install_loguru_session_sink(context: ParlotContext, agent_id: str) -> None:
    """Pipecat logs via loguru; bridge into Parlot session logs.

    Level is DEBUG so bootstrap ``logs.min_level`` (often DEBUG) can filter —
    Pipecat's useful pipeline lines are mostly DEBUG.
    """
    try:
        from loguru import logger as loguru_logger
    except ImportError:
        return

    import logging as stdlib_logging

    from parlot.core.session_logs import SessionLogHandler

    collector = context.session_logs
    # Reuse the installed handler when present so format/flush stay consistent.
    bridge = collector._handler or SessionLogHandler(collector)
    if bridge.formatter is None:
        bridge.setFormatter(stdlib_logging.Formatter("%(message)s"))

    def _sink(message) -> None:  # noqa: ANN001
        try:
            record = message.record
            level = str(record["level"].name)
            # Map loguru-only levels onto stdlib.
            levelno = getattr(stdlib_logging, level, None)
            if not isinstance(levelno, int):
                levelno = (
                    stdlib_logging.DEBUG
                    if level == "TRACE"
                    else stdlib_logging.INFO
                )
            file_info = record.get("file")
            pathname = ""
            if file_info is not None:
                pathname = str(getattr(file_info, "path", None) or file_info or "")
            lr = stdlib_logging.LogRecord(
                name=str(record.get("name") or "pipecat"),
                level=levelno,
                pathname=pathname,
                lineno=int(record.get("line") or 0),
                msg=str(record.get("message") or ""),
                args=(),
                exc_info=None,
                func=str(record.get("function") or ""),
            )
            lr.created = float(record["time"].timestamp())
            # LogRecord.levelname is derived from levelno; SUCCESS→Level 25 needs help.
            if level not in (
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
                "CRITICAL",
                "WARN",
            ):
                lr.levelname = "INFO" if level == "SUCCESS" else level
            collector.handle_record(bridge, lr)
        except Exception:
            pass

    try:
        loguru_logger.add(
            _sink,
            level="DEBUG",
            format="{message}",
            filter=lambda _r: bool(agent_id),
        )
    except Exception:
        logger.debug("Could not install loguru session-log sink", exc_info=True)


def _build_provider(
    *,
    endpoint: str,
    api_key: str,
    service_name: Optional[str],
    service_version: Optional[str] = None,
    context: ParlotContext,
):
    from parlot.core.metrics import ParlotMetricsRecorder
    from parlot.core.provider import build_filtered_tracer_provider, build_resource

    from ._metrics import (
        build_meter_provider,
        configure_metrics_endpoint,
        set_metrics_recorder,
    )
    from ._processor import PipecatGenAIProcessor
    from .attrs import PIPECAT_FRAMEWORK

    provider = build_filtered_tracer_provider(
        endpoint=endpoint,
        api_key=api_key,
        service_name=service_name or "pipecat-agent",
        service_version=service_version,
        span_processors=(PipecatGenAIProcessor(context=context),),
    )
    try:
        resource = build_resource(
            service_name=service_name or "pipecat-agent",
            service_version=service_version,
        )
        configure_metrics_endpoint(endpoint, api_key, resource)
        meter_provider = build_meter_provider(endpoint, api_key, resource)
        set_metrics_recorder(
            ParlotMetricsRecorder(
                meter_provider,
                meter_name="parlot.instrumentation.pipecat",
                framework=PIPECAT_FRAMEWORK,
            )
        )
    except Exception:
        logger.debug("Could not enable Pipecat usage metrics exporter", exc_info=True)
    return provider


def _attach_processor_if_needed(provider: TracerProvider, context: ParlotContext) -> None:
    from parlot.core.provider import attach_span_processor_if_absent

    from ._processor import PipecatGenAIProcessor

    attach_span_processor_if_absent(
        provider,
        lambda: PipecatGenAIProcessor(context=context),
        processor_type=PipecatGenAIProcessor,
    )


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


def flush_session_logs() -> None:
    """Push any buffered session logs (call on session close)."""
    ctx = _parlot_context
    if ctx is None:
        return
    try:
        ctx.session_logs._try_flush(force=True)
    except Exception:
        logger.debug("session_logs flush failed", exc_info=True)


def configured_context() -> ParlotContext | None:
    return _parlot_context


def configured_record() -> bool | list[str] | None:
    return _configured_record


def register_recording_processor(processor: Any) -> None:
    """Track an active ``ParlotRecordingProcessor`` for close-time flush."""
    if processor is not None and processor not in _active_recorders:
        _active_recorders.append(processor)


def unregister_recording_processor(processor: Any) -> None:
    try:
        _active_recorders.remove(processor)
    except ValueError:
        pass


async def finish_active_recordings() -> None:
    """Fail-open flush of every registered recording processor."""
    recorders = list(_active_recorders)
    _active_recorders.clear()
    for proc in recorders:
        finish = getattr(proc, "finish", None)
        if finish is None:
            continue
        try:
            await finish()
        except Exception:
            logger.warning("parlot: recording finish failed", exc_info=True)


def close_session(conversation_id: str, *, reason: str = "completed") -> None:
    """Public helper to close a Pipecat-owned session by conversation_id."""
    from ._session import close_session as _close

    # Best-effort sync bridge: schedule finish if a loop is running.
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(finish_active_recordings())
    except RuntimeError:
        try:
            asyncio.run(finish_active_recordings())
        except Exception:
            logger.debug("parlot: sync recording finish skipped", exc_info=True)

    _close(conversation_id, reason=reason)
