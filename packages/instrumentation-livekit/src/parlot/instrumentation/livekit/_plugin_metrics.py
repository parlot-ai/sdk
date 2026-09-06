"""LiveKit AgentSession plugin metrics → Parlot OTLP usage.* and span token enrichment."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ._processor import LiveKitGenAIProcessor

logger = logging.getLogger("parlot.instrumentation.livekit")

_SKIP_PLUGIN_METRIC_TYPES = frozenset({"vad_metrics"})


@dataclass
class _PluginLlmUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_name: str = ""
    model_provider: str = ""


@dataclass
class _PluginMetricsState:
    by_speech_id: dict[str, list[_PluginLlmUsage]] = field(default_factory=dict)
    llm_queue: list[_PluginLlmUsage] = field(default_factory=list)


def _plugin_state(processor: "LiveKitGenAIProcessor") -> _PluginMetricsState:
    if not hasattr(processor, "_plugin_metrics_state"):
        processor._plugin_metrics_state = _PluginMetricsState()  # type: ignore[attr-defined]
    return processor._plugin_metrics_state  # type: ignore[attr-defined]


def _llm_usage_from_metrics(metrics_obj: Any) -> Optional[_PluginLlmUsage]:
    metric_type = str(getattr(metrics_obj, "type", "") or "")
    if metric_type != "llm_metrics":
        return None
    prompt = int(getattr(metrics_obj, "prompt_tokens", 0) or 0)
    completion = int(getattr(metrics_obj, "completion_tokens", 0) or 0)
    if prompt <= 0 and completion <= 0:
        return None
    from ._metrics import _usage_metadata

    model_name, model_provider = _usage_metadata(metrics_obj)
    return _PluginLlmUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        model_name=model_name,
        model_provider=model_provider,
    )


def handle_plugin_metrics_collected(
    processor: "LiveKitGenAIProcessor",
    metrics_obj: Any,
) -> None:
    """Map LiveKit plugin metrics to OTLP usage.* and speech_id token accumulator."""
    metric_type = str(getattr(metrics_obj, "type", "") or "")
    if metric_type in _SKIP_PLUGIN_METRIC_TYPES:
        return

    from ._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    if bootstrap is None or not bootstrap.state.parlot_session_id:
        return

    state = bootstrap.state
    metrics = processor._metrics  # type: ignore[attr-defined]
    if metrics is not None:
        metrics.record_usage_collected(state, metrics_obj)

    llm_usage = _llm_usage_from_metrics(metrics_obj)
    if llm_usage is None:
        return

    plugin_state = _plugin_state(processor)
    speech_id = str(getattr(metrics_obj, "speech_id", "") or "").strip()
    # Always enqueue for export-time FIFO (prefer_fifo=True). Also index by
    # speech_id for on_end matching when the span already carries lk.speech_id.
    plugin_state.llm_queue.append(llm_usage)
    if speech_id:
        plugin_state.by_speech_id.setdefault(speech_id, []).append(llm_usage)
        state.active_speech_id = speech_id


def resolve_llm_usage_for_span(
    processor: "LiveKitGenAIProcessor",
    *,
    speech_id: str = "",
    prefer_fifo: bool = False,
) -> Optional[_PluginLlmUsage]:
    """Resolve plugin LLM token usage for a span.

    ``prefer_fifo=True`` (export-time) consumes the FIFO queue in arrival order so
    multiple ``llm_node`` spans per speech each get the correct metrics row.
    """
    plugin_state = _plugin_state(processor)
    sid = speech_id.strip()
    if prefer_fifo:
        if plugin_state.llm_queue:
            usage = plugin_state.llm_queue.pop(0)
            if sid:
                queue = plugin_state.by_speech_id.get(sid)
                if queue and usage in queue:
                    queue.remove(usage)
                    if not queue:
                        del plugin_state.by_speech_id[sid]
            return usage
        return None
    if sid:
        queue = plugin_state.by_speech_id.get(sid)
        if queue:
            usage = queue.pop(0)
            if not queue:
                del plugin_state.by_speech_id[sid]
            if usage in plugin_state.llm_queue:
                plugin_state.llm_queue.remove(usage)
            return usage
    if plugin_state.llm_queue:
        return plugin_state.llm_queue.pop(0)
    return None


def install_emit_metrics_intercept(processor: "LiveKitGenAIProcessor") -> None:
    """Intercept AgentSession.emit for MetricsCollectedEvent → Parlot usage.* OTLP."""
    try:
        from livekit.agents import AgentSession
    except ImportError:
        return
    if getattr(AgentSession, "_parlot_emit_metrics_patched", False):
        return

    original_emit = AgentSession.emit

    def _patched_emit(self, event_name: str, ev: Any) -> None:
        original_emit(self, event_name, ev)  # type: ignore[arg-type]
        if event_name != "metrics_collected":
            return
        try:
            metrics_obj = getattr(ev, "metrics", None)
            if metrics_obj is not None:
                handle_plugin_metrics_collected(processor, metrics_obj)
            from ._session import get_job_bootstrap
            from ._telemetry_compare import compare_plugins_enabled, get_compare_logger

            bootstrap = get_job_bootstrap()
            if (
                compare_plugins_enabled()
                and bootstrap is not None
                and bootstrap.state.parlot_session_id
                and metrics_obj is not None
            ):
                get_compare_logger().log_plugin_metrics(
                    bootstrap.state.parlot_session_id,
                    metrics_obj=metrics_obj,
                )
        except Exception:
            logger.debug("emit metrics intercept failed", exc_info=True)

    setattr(AgentSession, "emit", _patched_emit)
    setattr(AgentSession, "_parlot_emit_metrics_patched", True)
    logger.debug("Patched AgentSession.emit for Parlot usage.* OTLP metrics")
