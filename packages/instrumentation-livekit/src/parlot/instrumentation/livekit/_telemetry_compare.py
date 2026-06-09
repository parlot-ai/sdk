"""Dev-only side-by-side JSONL logging for events vs spans vs plugin metrics."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("parlot.instrumentation.livekit")

_COMPARE_SPAN_NAMES = frozenset({
    "parlot.turn",
    "agent.handoff",
    "conversation.session",
    "user_turn",
    "agent_turn",
    "llm_node",
    "tts_node",
    "function_tool",
    "eou_detection",
})


def compare_enabled() -> bool:
    return os.getenv("PARLOT_TELEMETRY_COMPARE", "").lower() in ("1", "true", "yes")


def compare_plugins_enabled() -> bool:
    return compare_enabled() and os.getenv(
        "PARLOT_TELEMETRY_COMPARE_PLUGINS", ""
    ).lower() in ("1", "true", "yes")


def _default_compare_dir(session_id: str) -> Path:
    base = os.getenv("PARLOT_TELEMETRY_COMPARE_DIR", "./parlot-telemetry-compare")
    return Path(base) / session_id


def _serialize_metrics_obj(metrics_obj: Any) -> dict[str, Any]:
    if metrics_obj is None:
        return {}
    if isinstance(metrics_obj, dict):
        return dict(metrics_obj)
    out: dict[str, Any] = {}
    metric_type = getattr(metrics_obj, "type", None)
    if metric_type:
        out["type"] = str(metric_type)
    for key in (
        "speech_id",
        "request_id",
        "ttft",
        "ttfb",
        "prompt_tokens",
        "completion_tokens",
        "audio_duration",
        "characters_count",
        "end_of_turn_delay",
        "transcription_delay",
        "label",
        "model_name",
    ):
        val = getattr(metrics_obj, key, None)
        if val is not None:
            out[key] = val
    metadata = getattr(metrics_obj, "metadata", None)
    if metadata is not None:
        out["metadata"] = {
            "model_name": getattr(metadata, "model_name", None),
            "model_provider": getattr(metadata, "model_provider", None),
        }
    return out


@dataclass
class _SessionCompareState:
    session_id: str
    dir_path: Path
    event_turns: int = 0
    span_turns: int = 0
    plugin_events: int = 0
    event_tokens_in: int | None = None
    event_tokens_out: int | None = None
    span_tokens_in: int = 0
    span_tokens_out: int = 0
    event_latency_fields: set[str] = field(default_factory=set)
    span_latency_fields: set[str] = field(default_factory=set)
    _files: dict[str, Any] = field(default_factory=dict)

    def _file(self, name: str) -> Any:
        if name not in self._files:
            self.dir_path.mkdir(parents=True, exist_ok=True)
            self._files[name] = open(self.dir_path / name, "a", encoding="utf-8")
        return self._files[name]

    def write(self, path: str, *, category: str, data: dict[str, Any], turn_index: int | None = None) -> None:
        envelope = {
            "ts": time.time(),
            "session_id": self.session_id,
            "path": path,
            "category": category,
            "turn_index": turn_index,
            "data": data,
        }
        self._file(f"{path}.jsonl").write(json.dumps(envelope, default=str) + "\n")

    def close(self) -> None:
        for handle in self._files.values():
            handle.close()
        self._files.clear()


class TelemetryCompareLogger:
    """Per-session compare logger; no-op when PARLOT_TELEMETRY_COMPARE is unset."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionCompareState] = {}

    def _state(self, session_id: str) -> _SessionCompareState | None:
        if not compare_enabled() or not session_id:
            return None
        state = self._sessions.get(session_id)
        if state is None:
            state = _SessionCompareState(
                session_id=session_id,
                dir_path=_default_compare_dir(session_id),
            )
            self._sessions[session_id] = state
        return state

    def log_event(
        self,
        session_id: str,
        *,
        category: str,
        data: dict[str, Any],
        turn_index: int | None = None,
    ) -> None:
        state = self._state(session_id)
        if state is None:
            return
        if category == "conversation_item_added":
            role = data.get("role")
            if role in ("user", "assistant"):
                state.event_turns += 1
            metrics = data.get("metrics") or {}
            if isinstance(metrics, dict):
                state.event_latency_fields.update(metrics.keys())
        if category == "session_usage_updated":
            state.event_tokens_in = data.get("total_input_tokens")
            state.event_tokens_out = data.get("total_output_tokens")
        state.write("events", category=category, data=data, turn_index=turn_index)

    def log_span(self, session_id: str, *, span_name: str, attrs: dict[str, Any]) -> None:
        if span_name not in _COMPARE_SPAN_NAMES:
            return
        state = self._state(session_id)
        if state is None:
            return
        if span_name in ("user_turn", "agent_turn"):
            state.span_turns += 1
        latency_keys = []
        for key in (
            "lk.e2e_latency",
            "lk.response_ttft",
            "lk.tts_ttfb",
            "lk.transcription_delay",
            "lk.end_of_turn_delay",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
        ):
            if key in attrs:
                latency_keys.append(key)
        if "gen_ai.usage.input_tokens" in attrs:
            try:
                state.span_tokens_in += int(attrs["gen_ai.usage.input_tokens"])
            except (TypeError, ValueError):
                pass
        if "gen_ai.usage.output_tokens" in attrs:
            try:
                state.span_tokens_out += int(attrs["gen_ai.usage.output_tokens"])
            except (TypeError, ValueError):
                pass
        state.span_latency_fields.update(latency_keys)
        state.write(
            "spans",
            category=span_name,
            data={"attributes": attrs, "latency_keys": latency_keys},
        )

    def log_plugin_metrics(self, session_id: str, *, metrics_obj: Any) -> None:
        state = self._state(session_id)
        if state is None:
            return
        payload = _serialize_metrics_obj(metrics_obj)
        state.plugin_events += 1
        state.write(
            "plugins",
            category=str(payload.get("type", "unknown")),
            data=payload,
            turn_index=None,
        )

    def finalize_session(self, session_id: str) -> None:
        state = self._sessions.pop(session_id, None)
        if state is None:
            return
        summary = {
            "session_id": session_id,
            "event_turns": state.event_turns,
            "span_turns": state.span_turns,
            "plugin_events": state.plugin_events,
            "event_tokens_in": state.event_tokens_in,
            "event_tokens_out": state.event_tokens_out,
            "span_tokens_in": state.span_tokens_in,
            "span_tokens_out": state.span_tokens_out,
            "event_latency_fields": sorted(state.event_latency_fields),
            "span_latency_fields": sorted(state.span_latency_fields),
        }
        state.dir_path.mkdir(parents=True, exist_ok=True)
        (state.dir_path / "summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        state.close()
        logger.debug("parlot telemetry compare summary written: %s", state.dir_path)


_compare_logger = TelemetryCompareLogger()


def get_compare_logger() -> TelemetryCompareLogger:
    return _compare_logger


def install_emit_compare_intercept() -> None:
    """Intercept AgentSession.emit for MetricsCollectedEvent (compare-only)."""
    if not compare_plugins_enabled():
        return
    try:
        from livekit.agents import AgentSession
    except ImportError:
        return
    if getattr(AgentSession, "_parlot_emit_compare_patched", False):
        return

    original_emit = AgentSession.emit

    def _patched_emit(self, event_name: str, ev: Any) -> None:
        original_emit(self, event_name, ev)
        if event_name != "metrics_collected":
            return
        try:
            from ._session import get_job_bootstrap

            bootstrap = get_job_bootstrap()
            if bootstrap is None:
                return
            session_id = bootstrap.state.parlot_session_id
            metrics_obj = getattr(ev, "metrics", None)
            if session_id and metrics_obj is not None:
                _compare_logger.log_plugin_metrics(session_id, metrics_obj=metrics_obj)
        except Exception:
            logger.debug("emit compare intercept failed", exc_info=True)

    AgentSession.emit = _patched_emit
    AgentSession._parlot_emit_compare_patched = True
    logger.debug("Patched AgentSession.emit for telemetry compare (plugins.jsonl)")
