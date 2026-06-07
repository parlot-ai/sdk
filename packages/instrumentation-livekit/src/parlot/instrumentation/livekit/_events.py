"""
LiveKit AgentSession event bridge — semantic/commit layer for Parlot telemetry.

Translates LiveKit events into Parlot turn roots, session aggregates, and span
enrichment state. Operational pipeline detail remains on OTel spans.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_CREATED_AT,
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_ITEM_ID,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_GEN_AI_OP_NAME,
    ATTR_STT_SPEAKER_ID,
    ATTR_TURN_INTERRUPTED,
    SPAN_AGENT_HANDOFF,
)

from parlot.instrumentation.livekit.attrs import ATTR_DIAR_SOURCE_STT_EVENT
from parlot.instrumentation.livekit._platform_refs import _job_room_fields, _str_field
from parlot.instrumentation.livekit._recording_guard import agent_name_from_ctx

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

    from ._processor import LiveKitGenAIProcessor

logger = logging.getLogger("parlot.instrumentation.livekit")

_CLOSE_REASON_MAP = {
    "participant_disconnected": "participant_disconnected",
    "user_initiated": "user_initiated",
    "error": "error",
    "task_completed": "task_completed",
    "job_shutdown": "job_shutdown",
}


def _message_text(item: Any) -> str:
    text = getattr(item, "text_content", None)
    if text is None:
        text = getattr(item, "textContent", None)
    if text:
        return str(text).strip()

    content = getattr(item, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if hasattr(part, "text"):
                text_part = str(getattr(part, "text", "")).strip()
                if text_part:
                    parts.append(text_part)
                continue
            transcript = getattr(part, "transcript", None)
            if transcript:
                parts.append(str(transcript).strip())
        return " ".join(p for p in parts if p).strip()
    return ""


def _item_metrics(item: Any) -> dict[str, float]:
    metrics = getattr(item, "metrics", None)
    if metrics is None:
        return {}
    if isinstance(metrics, dict):
        raw = metrics
    else:
        raw = {}
        for key in (
            "e2e_latency",
            "llm_ttft",
            "tts_ttfb",
            "transcription_delay",
            "eou_delay",
            "end_of_turn_delay",
        ):
            val = getattr(metrics, key, None)
            if val is not None:
                raw[key] = val

    out: dict[str, float] = {}
    for key, val in raw.items():
        try:
            out[key] = float(val)
        except (TypeError, ValueError):
            continue
    if "end_of_turn_delay" in out and "eou_delay" not in out:
        out["eou_delay"] = out["end_of_turn_delay"]
    return out


def _normalize_close_reason(reason: Any) -> str:
    raw = reason
    if hasattr(reason, "value"):
        raw = getattr(reason, "value", reason)
    key = str(raw or "").strip().lower()
    if "." in key:
        key = key.split(".")[-1]
    return _CLOSE_REASON_MAP.get(key, key or "unknown")


def _agent_state_value(state: Any) -> str:
    if state is None:
        return ""
    val = getattr(state, "value", state)
    return str(val).lower().split(".")[-1]


def _resolve_job_context(session: Any) -> Any | None:
    try:
        from livekit.agents.job import get_job_context

        ctx = get_job_context()
        if ctx is not None:
            return ctx
    except Exception:
        pass
    return getattr(session, "_parlot_job_ctx", None)


class LiveKitEventBridge:
    """Subscribes to AgentSession events and drives Parlot semantic telemetry."""

    def __init__(self, processor: "LiveKitGenAIProcessor", tracer: "Tracer") -> None:
        self._processor = processor
        self._tracer = tracer
        self._session: Any | None = None

    def install(self, session: Any) -> None:
        self._session = session
        self._processor.set_turn_source("events")

        @session.on("conversation_item_added")
        def _on_conversation_item_added(ev: Any) -> None:
            try:
                self._on_conversation_item_added(ev)
            except Exception:
                logger.debug("conversation_item_added handler failed", exc_info=True)

        @session.on("user_input_transcribed")
        def _on_user_input_transcribed(ev: Any) -> None:
            try:
                self._on_user_input_transcribed(ev)
            except Exception:
                logger.debug("user_input_transcribed handler failed", exc_info=True)

        @session.on("function_tools_executed")
        def _on_function_tools_executed(ev: Any) -> None:
            try:
                self._on_function_tools_executed(ev)
            except Exception:
                logger.debug("function_tools_executed handler failed", exc_info=True)

        @session.on("session_usage_updated")
        def _on_session_usage_updated(ev: Any) -> None:
            try:
                self._on_session_usage_updated(ev)
            except Exception:
                logger.debug("session_usage_updated handler failed", exc_info=True)

        @session.on("error")
        def _on_error(ev: Any) -> None:
            try:
                self._on_error(ev)
            except Exception:
                logger.debug("error handler failed", exc_info=True)

        @session.on("agent_state_changed")
        def _on_agent_state_changed(ev: Any) -> None:
            try:
                self._on_agent_state_changed(ev)
            except Exception:
                logger.debug("agent_state_changed handler failed", exc_info=True)

        @session.on("close")
        def _on_close(ev: Any) -> None:
            try:
                self._on_close(ev)
            except Exception:
                logger.debug("close handler failed", exc_info=True)

    def _on_agent_state_changed(self, ev: Any) -> None:
        session = self._session
        if session is None:
            return

        old_state = _agent_state_value(getattr(ev, "old_state", None))
        new_state = _agent_state_value(getattr(ev, "new_state", None))

        if old_state == "listening" and new_state == "initializing":
            session._parlot_shutdown_reset = True
            return

        if old_state != "initializing" or new_state != "listening":
            return

        if getattr(session, "_parlot_shutdown_reset", False):
            return

        from ._session import bootstrap_session, get_job_bootstrap, schedule_post_bootstrap_connect

        if get_job_bootstrap() is not None:
            return

        ctx = _resolve_job_context(session)
        vendor_job_id = ""
        room_name = ""
        room_sid = ""
        worker_agent_name = ""
        if ctx is not None:
            vendor_job_id, room_name, room_sid = _job_room_fields(ctx)
            worker_agent_name = agent_name_from_ctx(ctx)

        if not room_name:
            room_name = _str_field(getattr(session, "room", None), "name")
        if not room_sid:
            room_sid = _str_field(getattr(session, "room", None), "sid", "id")

        bootstrap_session(
            self._processor,
            vendor_job_id=vendor_job_id,
            room_name=room_name,
            room_sid=room_sid,
            worker_agent_name=worker_agent_name,
        )
        session._parlot_bootstrapped = True
        schedule_post_bootstrap_connect(ctx or getattr(session, "_parlot_job_ctx", None))

    def _on_conversation_item_added(self, ev: Any) -> None:
        item = getattr(ev, "item", None)
        if item is None:
            return

        item_type = str(getattr(item, "type", "") or "")
        if item_type == "agent_handoff":
            self._emit_handoff_span(item)
            return

        role = str(getattr(item, "role", "") or "").lower()
        if role not in ("user", "assistant"):
            return

        item_id = str(getattr(item, "id", "") or "")
        if item_id and not self._processor.mark_conversation_item_committed(item_id):
            return

        text = _message_text(item)
        if not text:
            return

        interrupted = bool(getattr(item, "interrupted", False))
        metrics = _item_metrics(item)

        if role == "user":
            self._processor.commit_user_message(
                text,
                interrupted=interrupted,
                metrics=metrics,
            )
        else:
            self._processor.commit_agent_message(
                text,
                interrupted=interrupted,
                metrics=metrics,
            )

    def _emit_handoff_span(self, item: Any) -> None:
        item_id = str(getattr(item, "id", "") or "")
        if item_id and item_id in self._processor.committed_handoff_item_ids():
            return
        if item_id:
            self._processor.mark_handoff_item_committed(item_id)

        old_id = getattr(item, "old_agent_id", None)
        new_id = getattr(item, "new_agent_id", None)

        with self._tracer.start_as_current_span(SPAN_AGENT_HANDOFF) as span:
            if old_id:
                span.set_attribute(ATTR_AGENT_TRANSFER_FROM, str(old_id))
            new_id = getattr(item, "new_agent_id", None)
            if new_id:
                span.set_attribute(ATTR_AGENT_TRANSFER_TO, str(new_id))
            span.set_attribute(ATTR_GEN_AI_OP_NAME, "agent_handoff")
            if item_id:
                span.set_attribute(ATTR_AGENT_TRANSFER_ITEM_ID, item_id)
            created_at = getattr(item, "created_at", None)
            if created_at is not None:
                span.set_attribute(ATTR_AGENT_TRANSFER_CREATED_AT, float(created_at))

        if self._processor.turn_source == "events":
            self._processor.record_handoff_from_event(
                from_agent=str(old_id) if old_id else "",
                to_agent=str(new_id) if new_id else "",
            )

    def _on_user_input_transcribed(self, ev: Any) -> None:
        if not getattr(ev, "is_final", True):
            return
        speaker_id = getattr(ev, "speaker_id", None)
        language = getattr(ev, "language", None)
        self._processor.note_user_transcription_meta(
            speaker_id=str(speaker_id) if speaker_id else "",
            language=str(language) if language else "",
        )

    def _on_function_tools_executed(self, ev: Any) -> None:
        zipped = getattr(ev, "zipped", None)
        if callable(zipped):
            pairs = list(cast(Iterable[Any], zipped()))
        else:
            calls = cast(list[Any], getattr(ev, "function_calls", None) or [])
            outputs = cast(list[Any], getattr(ev, "function_call_outputs", None) or [])
            pairs = list(zip(calls, outputs))
        if pairs:
            self._processor.note_function_tools_executed(len(pairs))

    def _on_session_usage_updated(self, ev: Any) -> None:
        usage = getattr(ev, "usage", None)
        if usage is None:
            return
        model_usage = getattr(usage, "model_usage", None) or []
        total_in = 0
        total_out = 0
        for entry in model_usage:
            total_in += int(getattr(entry, "input_tokens", 0) or 0)
            total_out += int(getattr(entry, "output_tokens", 0) or 0)
        self._processor.apply_session_usage(total_in, total_out)

    def _on_error(self, ev: Any) -> None:
        err = getattr(ev, "error", None)
        if err is None:
            return
        recoverable = bool(getattr(err, "recoverable", True))
        message = str(err)
        self._processor.note_session_error(message, recoverable=recoverable)

    def _on_close(self, ev: Any) -> None:
        from ._session import emit_parlot_session_close_span, get_job_bootstrap

        bootstrap = get_job_bootstrap()
        if bootstrap is None or bootstrap.close_span_done:
            return

        reason = _normalize_close_reason(getattr(ev, "reason", "unknown"))
        error = getattr(ev, "error", None)
        close_error = str(error) if error else None
        if close_error is None:
            close_error = self._processor.pop_pending_close_error()

        from ._session import finalize_session_close_from_hook

        finalize_session_close_from_hook(
            bootstrap,
            close_reason=reason,
            close_error=close_error,
        )

        session = self._session
        if session is not None:
            session._parlot_job_ctx = None
            session._parlot_shutdown_reset = False
            session._parlot_bootstrapped = False


def install_session_hooks(
    session: Any,
    processor: "LiveKitGenAIProcessor",
    tracer: "Tracer",
) -> None:
    """Install all AgentSession event listeners for Parlot instrumentation."""
    LiveKitEventBridge(processor, tracer).install(session)
