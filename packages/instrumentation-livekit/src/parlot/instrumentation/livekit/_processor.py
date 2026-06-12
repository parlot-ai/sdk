"""
LiveKitGenAIProcessor — enriches LiveKit Agents OTel spans in-place.

Turn boundaries (livekit-agents 1.5.9): ``user_turn`` and ``agent_turn``.
``eou_detection`` is a child model span; ``drain_agent_activity`` is lifecycle only.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, FrozenSet, Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Status, StatusCode, Tracer
from opentelemetry.util.types import AttributeValue

from parlot.core.logging import format_attrs_for_log
from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_AGENT_INSTRUCTIONS_EXCERPT,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_STAGE,
    ATTR_AGENT_TOOL_CALL_INDEX,
    ATTR_AGENT_TOOL_IS_ERROR,
    ATTR_AGENT_TOOL_NAME,
    ATTR_AGENT_TOOL_NAMES,
    ATTR_AGENT_TOOL_TIMING_CORRECTED,
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_LATENCY_MS,
    ATTR_AGENT_TRANSFER_SEQUENCE,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOOL_DURATION_MS,
    ATTR_GEN_AI_TOOL_IS_HANDOFF,
    ATTR_GEN_AI_TTS_TTFB_S,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_TOOL_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
    ATTR_SESSION_AGENT_CHAIN,
    ATTR_SESSION_AMD,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_HANDOFF_COUNT,
    ATTR_SESSION_ID,
    ATTR_SESSION_LANGUAGES,
    ATTR_SESSION_RECORDING_ANCHOR_WALL_MS,
    ATTR_SESSION_TOOL_CALL_COUNT,
    ATTR_SESSION_TOTAL_INPUT_TOKENS,
    ATTR_SESSION_TOTAL_OUTPUT_TOKENS,
    ATTR_SESSION_TURN_COUNT,
    ATTR_SESSION_USER_ID,
    SPAN_PARLOT_SESSION_CLOSE,
    ATTR_STT_SPEAKER_ID,
    ATTR_DIAR_SOURCE_AGENT_ID,
    ATTR_DIAR_SOURCE_STT_SPEAKER_ID,
    ATTR_TURN_PARTICIPANT_ID_CALLER,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_E2E_LATENCY_S,
    ATTR_TURN_EOU_DELAY_S,
    ATTR_TURN_INDEX,
    ATTR_TURN_LLM_TTFT_S,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_TRANSCRIPTION_DELAY_S,
    ATTR_TURN_USER_TEXT,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_INTERRUPTED,
    ATTR_VOICE_STT_CONFIDENCE,
    ATTR_EXCEPTION_TYPE,
    ATTR_TOOL_INPUT_PAYLOAD,
    ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
    ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW,
    ATTR_PARTICIPANT_CHANNEL_IDENTITY,
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_VOICE_AMD_CATEGORY,
    ATTR_VOICE_EOU_LANGUAGE,
    SPAN_AGENT_HANDOFF,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_AMD_CATEGORY,
    ATTR_DIAR_SOURCE_TEXT_INPUT,
    ATTR_DIAR_SOURCE_VAD,
    ATTR_EOU_LANGUAGE,
    ATTR_END_OF_TURN_DELAY,
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_AGENT_NAME,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_E2E_LATENCY,
    ATTR_LK_FUNCTION_TOOLS,
    ATTR_LK_INSTRUCTIONS,
    ATTR_LK_FNC_TOOL_ARGS,
    ATTR_LK_FNC_TOOL_ERROR,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_INTERRUPTED,
    ATTR_LK_IS_INTERRUPTION,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_RESPONSE_TTFB,
    ATTR_LK_RESPONSE_TTFT,
    ATTR_LK_SPEECH_ID,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
    ATTR_LK_TTS_INPUT_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_LK_USER_TRANSCRIPT,
    ATTR_DIAR_SOURCE_STT_EVENT,
    ATTR_PARTICIPANT_IDENTITY,
    ATTR_TRANSCRIPT_CONFIDENCE,
    ATTR_TRANSCRIPTION_DELAY,
    METADATA_JOB_ID,
    METADATA_ROOM_ID,
)
from ._chat_ctx import instructions_excerpt_from_chat_ctx
from ._span_stage import livekit_agent_stage_for_span
from ._platform_refs import lookup_room_context, stamp_livekit_platform_refs
from ._session import (
    SPAN_CONVERSATION_SESSION,
    get_job_bootstrap,
    handle_conversation_session_on_end,
)
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.session import SessionState as _BaseSessionState
from ._turn_traces import emit_turn_root_span

logger = logging.getLogger("parlot.instrumentation.livekit")

_MAX_TOOL_PAYLOAD_CHARS = 8192
_ASYNC_TOOL_MIN_DURATION_NS = 30_000_000_000
_EXECUTION_START_GAP_NS = 5_000_000_000
_TOOL_PREVIEW_CHARS = 512
_INSTRUCTIONS_EXCERPT_CHARS = 2000

_AGENT_PIPELINE_SPANS: FrozenSet[str] = frozenset({
    "user_turn",
    "agent_turn",
    "llm_node",
    "llm_request",
    "llm_request_run",
    "tts_node",
    "tts_request_run",
    "function_tool",
    "amd",
})

_USER_TURN_SPAN_NAMES: FrozenSet[str] = frozenset({
    "user_turn",
    "eou_detection",
})

_AGENT_LABEL_SPANS: FrozenSet[str] = frozenset({
    "job_entrypoint",
    "agent_session",
    "start_agent_activity",
    "on_enter",
    "on_exit",
    "pause_agent_activity",
    "resume_agent_activity",
    "agent_turn",
    "drain_agent_activity",
    SPAN_AGENT_HANDOFF,
})

_AMD_CATEGORY_TO_CONTACT_TYPE: dict[str, str] = {
    "human": "human",
    "machine-ivr": "ivr",
    "machine-vm": "voicemail",
    "machine-unavailable": "unavailable",
    "uncertain": "unknown",
}


@dataclass
class _LiveKitSessionState(_BaseSessionState):
    agent_chain: list[str] = field(default_factory=list)
    worker_agent_name: str = ""
    pending_handoff_end_ns: int = 0
    parlot_session_id: str = ""
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    turn_trace_by_index: dict[int, str] = field(default_factory=dict)
    turn_root_span_by_index: dict[int, str] = field(default_factory=dict)
    open_agent_turn_index: Optional[int] = None
    amd: str = ""
    recording_anchor_wall_ms: Optional[int] = None
    languages_seen: set[str] = field(default_factory=set)
    user_id: str = ""
    pending_tts_ttfb_s: Optional[float] = None
    committed_item_ids: set[str] = field(default_factory=set)
    committed_handoff_ids: set[str] = field(default_factory=set)
    pending_user_speaker_id: str = ""
    pending_user_language: str = ""
    active_speech_id: str = ""
    last_user_input_modality: str = ""
    usage_from_events: bool = False
    metrics_recorded_turns: set[int] = field(default_factory=set)
    pending_close_error: str = ""
    user_text_by_turn: dict[int, str] = field(default_factory=dict)
    agent_text_by_turn: dict[int, str] = field(default_factory=dict)
    last_user_turn_index: int = 0
    tool_execution_ns_queue: list[int] = field(default_factory=list)


class LiveKitGenAIProcessor(ParlotBaseProcessor):
    """Enriches LiveKit Agent spans in-place with Parlot conventions."""

    def __init__(
        self,
        capture_content: bool = True,
        handoff_tool_names: Optional[set[str]] = None,
    ) -> None:
        self._capture_content = capture_content
        self._handoff_tools = handoff_tool_names or set()
        self._sessions: dict[str, _LiveKitSessionState] = {}
        self._turn_trace_registry: dict[str, dict[int, tuple[str, str]]] = {}
        self._tracer: Tracer | None = None
        self._metrics = None
        self._turn_source: str = "spans"

    def on_start(self, span, parent_context=None) -> None:
        super().on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        super().on_end(span)
        try:
            logger.debug(
                "on_end: %s attrs: %s",
                span.name,
                format_attrs_for_log(span.attributes),
            )
            name = span.name
            if name == SPAN_CONVERSATION_SESSION:
                handle_conversation_session_on_end()
                return
            self._enrich(span)
            self._log_compare_span(span)
        except Exception:
            logger.exception("LiveKitGenAIProcessor failed on span %r", span.name)

    def set_tracer(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def set_metrics(self, metrics) -> None:
        self._metrics = metrics

    def set_turn_source(self, source: str) -> None:
        if source in ("spans", "events"):
            self._turn_source = source

    @property
    def turn_source(self) -> str:
        return self._turn_source

    def enrich_spans_for_export(self, spans: list[ReadableSpan]) -> None:
        """Deferred enrichment after plugin metrics_collected (export-time)."""
        self._correct_function_tool_timing(spans)

        llm_spans = sorted(
            (s for s in spans if s.name == "llm_node"),
            key=lambda s: s.end_time or 0,
        )
        for span in llm_spans:
            attrs = span.attributes or {}
            if not attrs.get(ATTR_LK_SPEECH_ID):
                bootstrap = get_job_bootstrap()
                speech_id = ""
                if bootstrap is not None:
                    speech_id = bootstrap.state.active_speech_id.strip()
                if speech_id:
                    self._set(span, ATTR_LK_SPEECH_ID, speech_id)
            self._apply_plugin_llm_usage_to_span(
                span, span.attributes or {}, prefer_fifo=True
            )

        from ._telemetry_compare import compare_enabled, get_compare_logger

        if not compare_enabled():
            return
        bootstrap = get_job_bootstrap()
        if bootstrap is None or not bootstrap.state.parlot_session_id:
            return
        session_id = bootstrap.state.parlot_session_id
        for span in spans:
            if span.name == "llm_node":
                get_compare_logger().accumulate_export_tokens(
                    session_id,
                    span_name=span.name or "",
                    attrs=dict(span.attributes or {}),
                )

    def _log_compare_span(self, span: ReadableSpan) -> None:
        from ._session import get_job_bootstrap
        from ._telemetry_compare import get_compare_logger

        bootstrap = get_job_bootstrap()
        if bootstrap is None or not bootstrap.state.parlot_session_id:
            return
        attrs = span.attributes or {}
        get_compare_logger().log_span(
            bootstrap.state.parlot_session_id,
            span_name=span.name or "",
            attrs=dict(attrs),
        )

    def mark_conversation_item_committed(self, item_id: str) -> bool:
        """Return False if this conversation item was already processed."""
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return False
        state = bootstrap.state
        if item_id in state.committed_item_ids:
            return False
        state.committed_item_ids.add(item_id)
        return True

    def mark_handoff_item_committed(self, item_id: str) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        bootstrap.state.committed_handoff_ids.add(item_id)

    def committed_handoff_item_ids(self) -> set[str]:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return set()
        return bootstrap.state.committed_handoff_ids

    def record_handoff_from_event(
        self, *, from_agent: str = "", to_agent: str = ""
    ) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        state.handoff_count += 1
        if to_agent and (not state.agent_chain or state.agent_chain[-1] != to_agent):
            state.agent_chain.append(to_agent)

    def note_user_transcription_meta(
        self, *, speaker_id: str = "", language: str = ""
    ) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        if speaker_id:
            state.pending_user_speaker_id = speaker_id
        if language:
            state.pending_user_language = language
            state.languages_seen.add(language)

    def note_function_tools_executed(self, count: int) -> None:
        if count <= 0:
            return
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        executed_ns = time.time_ns()
        for _ in range(count):
            state.tool_execution_ns_queue.append(executed_ns)
        state.tool_call_count += count

    def _correct_function_tool_timing(self, spans: list[ReadableSpan]) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        queue = list(bootstrap.state.tool_execution_ns_queue)
        if not queue:
            return

        tool_spans = sorted(
            (s for s in spans if s.name == "function_tool"),
            key=lambda s: s.end_time or 0,
        )
        for span in tool_spans:
            if not queue:
                break
            executed_ns = queue.pop(0)
            if span.start_time is None or span.end_time is None:
                continue
            duration_ns = span.end_time - span.start_time
            start_gap_ns = executed_ns - span.start_time
            should_correct = (
                duration_ns >= _ASYNC_TOOL_MIN_DURATION_NS
                or start_gap_ns >= _EXECUTION_START_GAP_NS
            )
            if not should_correct or executed_ns >= span.end_time:
                continue
            span._start_time = executed_ns
            new_duration_ms = round((span.end_time - executed_ns) / 1_000_000, 2)
            self._set(span, ATTR_GEN_AI_TOOL_DURATION_MS, new_duration_ms)
            self._set(span, ATTR_AGENT_TOOL_TIMING_CORRECTED, True)

    def apply_session_usage(self, total_in: int, total_out: int) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        state.total_input_tokens = max(total_in, 0)
        state.total_output_tokens = max(total_out, 0)
        state.usage_from_events = True

    def note_session_error(self, message: str, *, recoverable: bool) -> None:
        if not recoverable and message:
            bootstrap = get_job_bootstrap()
            if bootstrap is not None:
                bootstrap.state.pending_close_error = message

    def pop_pending_close_error(self) -> str | None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return None
        err = bootstrap.state.pending_close_error.strip()
        bootstrap.state.pending_close_error = ""
        return err or None

    def commit_user_message(
        self,
        text: str,
        *,
        interrupted: bool = False,
        metrics: dict[str, float] | None = None,
    ) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None or not text.strip():
            return
        state = bootstrap.state
        state.turn_count += 1
        user_turn_index = state.turn_count
        committed_text = text.strip()
        state.user_text_by_turn[user_turn_index] = committed_text
        state.last_user_turn_index = user_turn_index
        participant_id, diarization_source = self._resolve_user_participant_from_state(
            state
        )
        agent_hint = state.agent_label or state.worker_agent_name
        modality = self._modality_for_user_text(text, state)
        state.last_user_input_modality = modality
        self._emit_turn_trace(
            state,
            turn_index=user_turn_index,
            role="user",
            participant_id=participant_id,
            diarization_source=diarization_source,
            input_modality=modality,
            agent_hint=agent_hint,
            turn_metrics=metrics,
            interrupted=interrupted,
        )
        self._emit_committed_user_utterance_span(
            state,
            turn_index=user_turn_index,
            text=committed_text,
            modality=modality,
            participant_id=participant_id,
            diarization_source=diarization_source,
        )
        state.open_agent_turn_index = user_turn_index + 1
        state.pending_user_speaker_id = ""
        state.pending_user_language = ""
        self._record_turn_metrics_from_event(
            state,
            turn_index=user_turn_index,
            metrics=metrics or {},
            interrupted=interrupted,
            participant_role="user",
        )

    def commit_agent_message(
        self,
        text: str,
        *,
        interrupted: bool = False,
        metrics: dict[str, float] | None = None,
    ) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None or not text.strip():
            return
        state = bootstrap.state
        turn_index = state.open_agent_turn_index or (state.turn_count + 1)
        state.agent_text_by_turn[turn_index] = text.strip()
        agent_id = self._active_agent_id(state, {})
        self._emit_turn_trace(
            state,
            turn_index=turn_index,
            role="agent",
            participant_id=agent_id,
            label=agent_id,
            diarization_source=ATTR_DIAR_SOURCE_AGENT_ID,
            input_modality=state.last_user_input_modality or "voice",
            agent_hint=agent_id,
            turn_metrics=metrics,
            interrupted=interrupted,
        )
        state.turn_count = turn_index
        state.open_agent_turn_index = None
        self._record_turn_metrics_from_event(
            state,
            turn_index=turn_index,
            metrics=metrics or {},
            interrupted=interrupted,
            participant_role="agent",
        )

    def _modality_for_user_text(self, text: str, state: _LiveKitSessionState) -> str:
        if state.pending_user_speaker_id or state.pending_user_language:
            return "voice"
        return "text"

    def _resolve_user_participant_from_state(
        self, state: _LiveKitSessionState
    ) -> tuple[str, str]:
        if state.pending_user_speaker_id:
            return state.pending_user_speaker_id, ATTR_DIAR_SOURCE_STT_EVENT
        return (
            ATTR_TURN_PARTICIPANT_ID_CALLER,
            self._user_turn_diarization_source("voice" if state.pending_user_language else "text"),
        )

    def _record_turn_metrics_from_event(
        self,
        state: _LiveKitSessionState,
        *,
        turn_index: int,
        metrics: dict[str, float],
        interrupted: bool,
        participant_role: str,
    ) -> None:
        if turn_index in state.metrics_recorded_turns:
            return
        if self._metrics and state.parlot_session_id and metrics:
            self._metrics.record_turn(
                state,
                e2e_latency_s=metrics.get("e2e_latency"),
                llm_ttft_s=metrics.get("llm_ttft"),
                tts_ttfb_s=metrics.get("tts_ttfb"),
                transcription_delay_s=metrics.get("transcription_delay"),
                eou_delay_s=metrics.get("eou_delay"),
                playback_latency_s=metrics.get("playback_latency"),
                interrupted=interrupted,
                participant_role=participant_role,
            )
            state.metrics_recorded_turns.add(turn_index)

    def lookup_turn_trace(
        self, session_id: str, turn_index: int
    ) -> tuple[str, str] | None:
        by_turn = self._turn_trace_registry.get(session_id)
        if not by_turn:
            return None
        return by_turn.get(turn_index)

    def _resolve_session_state(
        self, span: ReadableSpan, attrs: Mapping[str, AttributeValue]
    ) -> _LiveKitSessionState | None:
        bootstrap = get_job_bootstrap()
        if bootstrap is not None:
            return bootstrap.state
        sid = attrs.get(ATTR_SESSION_ID)
        if sid:
            state = self._sessions.get(str(sid))
            if state is not None:
                return state
        job_id = attrs.get(ATTR_LK_JOB_ID) or attrs.get(METADATA_JOB_ID)
        if job_id:
            state = self._sessions.get(str(job_id))
            if state is not None:
                return state
        name = span.name or ""
        if (
            name in _AGENT_PIPELINE_SPANS
            or name in _AGENT_LABEL_SPANS
            or job_id is not None
        ):
            logger.debug(
                "parlot: no session bootstrap for span %s (trace=%s); skipping enrich",
                name,
                self._trace_id_hex(span),
            )
            return None
        logger.error(
            "parlot: no session bootstrap for span %s (trace=%s)",
            name,
            self._trace_id_hex(span),
        )
        return None

    def _track_agent_label(
        self, state: _LiveKitSessionState, attrs: Mapping[str, AttributeValue]
    ) -> None:
        label = attrs.get(ATTR_LK_AGENT_LABEL) or attrs.get(ATTR_LK_AGENT_NAME)
        if label:
            label_str = str(label)
            self._maybe_update(state, "agent_label", label_str)

    def _active_agent_id(
        self,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue],
        *,
        label_override: str | None = None,
    ) -> str:
        if label_override:
            return str(label_override)
        label = attrs.get(ATTR_LK_AGENT_LABEL) or attrs.get(ATTR_LK_AGENT_NAME)
        if label:
            return str(label)
        if state.agent_label:
            return state.agent_label
        if state.worker_agent_name:
            return state.worker_agent_name
        if state.agent_chain:
            return state.agent_chain[-1]
        return "unknown"

    def _user_turn_index_for_events(
        self, state: _LiveKitSessionState, span_name: str
    ) -> Optional[int]:
        if span_name not in _USER_TURN_SPAN_NAMES:
            return None
        if state.last_user_turn_index:
            return state.last_user_turn_index
        if state.open_agent_turn_index is not None and state.open_agent_turn_index > 1:
            return state.open_agent_turn_index - 1
        return state.turn_count if state.turn_count else None

    def _active_turn_index(
        self, state: _LiveKitSessionState, span_name: str
    ) -> Optional[int]:
        if span_name == "job_entrypoint":
            return None
        user_turn_index = self._user_turn_index_for_events(state, span_name)
        if user_turn_index is not None:
            return user_turn_index
        if (
            state.open_agent_turn_index is not None
            and span_name in _AGENT_PIPELINE_SPANS
            and span_name not in _USER_TURN_SPAN_NAMES
        ):
            return state.open_agent_turn_index
        if state.turn_count:
            return state.turn_count
        return None

    def _enrich(self, span: ReadableSpan) -> None:
        name = span.name
        if name in ("parlot.turn", SPAN_PARLOT_SESSION_CLOSE, SPAN_CONVERSATION_SESSION):
            return
        attrs = span.attributes or {}
        state = self._resolve_session_state(span, attrs)
        if state is None:
            return

        explicit_job = attrs.get(ATTR_LK_JOB_ID) or attrs.get(METADATA_JOB_ID)
        if explicit_job:
            self._maybe_update(state, "session_id", explicit_job)
        self._maybe_update(state, "room_name", attrs.get(ATTR_LK_ROOM_NAME))
        self._maybe_update(state, "room_sid", attrs.get(ATTR_LK_ROOM_SID) or attrs.get(METADATA_ROOM_ID))

        if name in _AGENT_LABEL_SPANS:
            self._track_agent_label(state, attrs)

        if state.session_id and not state.room_sid:
            rn, rs = lookup_room_context(state.session_id)
            self._maybe_update(state, "room_name", rn or None)
            self._maybe_update(state, "room_sid", rs or None)

        if state.session_id:
            self._set(span, ATTR_LK_JOB_ID, state.session_id)
        if state.room_name:
            self._set(span, ATTR_LK_ROOM_NAME, state.room_name)
        if state.room_sid:
            self._set(span, ATTR_LK_ROOM_SID, state.room_sid)

        stamp_livekit_platform_refs(
            span,
            job_id=state.session_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )

        self._stamp_session_turn_attrs(span, state)
        self._set(span, ATTR_AGENT_FRAMEWORK, "livekit")
        stage = livekit_agent_stage_for_span(name)
        if stage:
            self._set(span, ATTR_AGENT_STAGE, stage)

        if name in ("llm_request", "llm_request_run"):
            self._enrich_llm_request(span, state)
        elif name == "llm_node":
            self._enrich_llm_node(span, state)
        elif name == "tts_node":
            self._enrich_tts_node(span, state)
        elif name == "tts_request_run":
            self._enrich_tts_request(span, state)
        elif name == "function_tool":
            self._enrich_function_tool(span, state)
        elif name == "user_turn":
            self._enrich_user_turn(span, state)
        elif name == "agent_turn":
            self._enrich_agent_turn(span, state)
        elif name == "drain_agent_activity":
            self._enrich_drain(span, state)
        elif name == "eou_detection":
            self._enrich_eou(span, state)
        elif name == "amd":
            self._enrich_amd(span, state)
        elif name == SPAN_AGENT_HANDOFF:
            self._enrich_handoff(span, state)

        if name in _AGENT_PIPELINE_SPANS:
            self._stamp_error_status_if_needed(span)

    def _stamp_error_status_if_needed(self, span: ReadableSpan) -> None:
        """Normalize failed pipeline spans to OTel ERROR status for OTLP export."""
        attrs = span.attributes or {}
        if attrs.get(ATTR_EXCEPTION_TYPE) or attrs.get(ATTR_LK_FNC_TOOL_ERROR):
            span._status = Status(StatusCode.ERROR)

    def _enrich_llm_request(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = _provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        input_tokens = _attr_int(attrs, ATTR_GEN_AI_IN_TOKENS)
        output_tokens = _attr_int(attrs, ATTR_GEN_AI_OUT_TOKENS)
        cached_tokens = _attr_int(attrs, ATTR_GEN_AI_CACHED_TOKENS)

        if not state.usage_from_events:
            state.total_input_tokens += input_tokens
            state.total_output_tokens += output_tokens

        if input_tokens and cached_tokens:
            self._set(
                span,
                ATTR_GEN_AI_CACHE_HIT_RATE,
                round(cached_tokens / input_tokens, 4),
            )

        if state.pending_handoff_end_ns and span.start_time:
            gap_ms = (span.start_time - state.pending_handoff_end_ns) / 1_000_000
            if 0 < gap_ms < 30_000:
                self._set(span, ATTR_AGENT_TRANSFER_LATENCY_MS, round(gap_ms, 2))
            state.pending_handoff_end_ns = 0

    def _enrich_llm_node(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = _provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "chat")

        if not attrs.get(ATTR_LK_SPEECH_ID) and state.active_speech_id:
            self._set(span, ATTR_LK_SPEECH_ID, state.active_speech_id)

        chat_raw = str(attrs.get(ATTR_LK_CHAT_CTX, ""))
        instructions = str(attrs.get(ATTR_LK_INSTRUCTIONS, "")).strip()
        if not instructions and chat_raw:
            instructions = instructions_excerpt_from_chat_ctx(
                chat_raw, max_chars=_INSTRUCTIONS_EXCERPT_CHARS
            )
        if instructions:
            self._set(span, ATTR_AGENT_INSTRUCTIONS_EXCERPT, instructions)

        tools = _coerce_str_sequence(attrs.get(ATTR_LK_FUNCTION_TOOLS))
        if tools:
            self._set(span, ATTR_AGENT_TOOL_NAMES, json.dumps(tools))

        user_text, assistant_text = _preview_from_chat_ctx(chat_raw)
        if user_text and self._turn_source != "events":
            self._set(span, ATTR_TURN_USER_TEXT, user_text)
        if assistant_text and self._turn_source != "events":
            self._set(span, ATTR_TURN_AGENT_TEXT, assistant_text)

        if self._capture_content:
            if user_text and self._turn_source != "events":
                self._add_event(
                    span,
                    EVENT_GEN_AI_USER_MESSAGE,
                    {"content": user_text},
                )
            if assistant_text and self._turn_source != "events":
                self._add_event(
                    span,
                    EVENT_GEN_AI_ASSISTANT_MESSAGE,
                    {"content": assistant_text},
                )

        self._apply_plugin_llm_usage_to_span(span, attrs)

    def _apply_plugin_llm_usage_to_span(
        self,
        span: ReadableSpan,
        attrs: Mapping[str, AttributeValue],
        *,
        prefer_fifo: bool = False,
    ) -> None:
        if attrs.get(ATTR_GEN_AI_IN_TOKENS) or attrs.get(ATTR_GEN_AI_OUT_TOKENS):
            return
        from ._plugin_metrics import resolve_llm_usage_for_span

        speech_id = str(attrs.get(ATTR_LK_SPEECH_ID, "") or "")
        usage = resolve_llm_usage_for_span(
            self, speech_id=speech_id, prefer_fifo=prefer_fifo
        )
        if usage is None:
            return
        if usage.prompt_tokens > 0:
            self._set(span, ATTR_GEN_AI_IN_TOKENS, usage.prompt_tokens)
        if usage.completion_tokens > 0:
            self._set(span, ATTR_GEN_AI_OUT_TOKENS, usage.completion_tokens)
        if usage.model_name and not attrs.get(ATTR_GEN_AI_MODEL):
            self._set(span, ATTR_GEN_AI_MODEL, usage.model_name)
        if usage.model_provider and not attrs.get(ATTR_GEN_AI_PROVIDER):
            self._set(span, ATTR_GEN_AI_PROVIDER, usage.model_provider)

    def _enrich_tts_node(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = _provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "text_to_speech")

        ttfb = attrs.get(ATTR_LK_RESPONSE_TTFB)
        if ttfb is not None:
            ttfb_s = float(ttfb)
            self._set(span, ATTR_GEN_AI_TTS_TTFB_S, ttfb_s)
            state.pending_tts_ttfb_s = ttfb_s

    def _enrich_tts_request(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "text_to_speech")

        if self._capture_content:
            text = attrs.get(ATTR_LK_TTS_INPUT_TEXT, "")
            if text:
                self._add_event(
                    span,
                    EVENT_GEN_AI_ASSISTANT_MESSAGE,
                    {"content": str(text), "modality": "text_for_speech"},
                )

    def _stamp_agent_identity(
        self,
        span: ReadableSpan,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue] | None = None,
        *,
        label_override: str | None = None,
    ) -> None:
        resolved: Mapping[str, AttributeValue] = (
            attrs if attrs is not None else (span.attributes or {})
        )
        if resolved.get(ATTR_GEN_AI_AGENT_NAME):
            return
        agent_id = self._active_agent_id(
            state, resolved, label_override=label_override
        )
        if agent_id != "unknown":
            self._set(span, ATTR_GEN_AI_AGENT_NAME, agent_id)

    def _enrich_function_tool(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        self._stamp_agent_identity(span, state, attrs)

        if self._turn_source != "events":
            state.tool_call_count += 1
            self._set(span, ATTR_AGENT_TOOL_CALL_INDEX, state.tool_call_count)
        elif state.tool_call_count:
            self._set(span, ATTR_AGENT_TOOL_CALL_INDEX, state.tool_call_count)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "execute_tool")

        tool_name = str(attrs.get(ATTR_LK_FNC_TOOL_NAME, ""))
        tool_output = str(attrs.get(ATTR_LK_FNC_TOOL_OUTPUT, ""))
        is_error = bool(attrs.get(ATTR_LK_FNC_TOOL_ERROR, False))
        if tool_name:
            self._set(span, ATTR_AGENT_TOOL_NAME, tool_name)
        self._set(span, ATTR_AGENT_TOOL_IS_ERROR, is_error)
        duration_ms = 0.0
        if span.end_time is not None and span.start_time is not None:
            duration_ms = round((span.end_time - span.start_time) / 1_000_000, 2)

        tool_args_raw = attrs.get(ATTR_LK_FNC_TOOL_ARGS, "")
        tool_args = str(tool_args_raw) if tool_args_raw else ""

        if self._capture_content and tool_args:
            payload = tool_args[:_MAX_TOOL_PAYLOAD_CHARS]
            self._set(span, ATTR_TOOL_INPUT_PAYLOAD, payload)
            self._set(
                span,
                ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
                payload[:_TOOL_PREVIEW_CHARS],
            )
        if self._capture_content and tool_output:
            out_preview = str(tool_output)[:_TOOL_PREVIEW_CHARS]
            self._set(span, ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW, out_preview)

        if span.end_time is not None and span.start_time is not None:
            self._set(span, ATTR_GEN_AI_TOOL_DURATION_MS, duration_ms)

        is_handoff = tool_name in self._handoff_tools or "AgentHandoff" in tool_output
        new_agent = _extract_new_agent(tool_output) if is_handoff else ""

        if is_handoff:
            state.handoff_count += 1
            self._set(span, ATTR_GEN_AI_TOOL_IS_HANDOFF, True)
            self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)

            if new_agent:
                self._set(span, ATTR_AGENT_TRANSFER_TO, new_agent)
                state.agent_label = new_agent
                if not state.agent_chain or state.agent_chain[-1] != new_agent:
                    state.agent_chain.append(new_agent)

            state.pending_handoff_end_ns = span.end_time or time.time_ns()

        if self._capture_content:
            tool_args = attrs.get(ATTR_LK_FNC_TOOL_ARGS, "")
            if tool_args:
                self._add_event(
                    span,
                    EVENT_GEN_AI_TOOL_MESSAGE,
                    {
                        "role": "tool",
                        "content": str(tool_args),
                        "direction": "input",
                        "name": tool_name,
                    },
                )
            if tool_output and not is_error:
                self._add_event(
                    span,
                    EVENT_GEN_AI_TOOL_MESSAGE,
                    {
                        "role": "tool",
                        "content": tool_output,
                        "direction": "output",
                        "name": tool_name,
                    },
                )

    def _sync_user_id_to_session(self, state: _LiveKitSessionState) -> None:
        if not state.user_id:
            return
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        session_span = bootstrap.session_span
        if session_span is not None and hasattr(session_span, "set_attribute"):
            session_span.set_attribute(ATTR_SESSION_USER_ID, state.user_id)

    def _capture_user_id(
        self,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue],
        *,
        span: ReadableSpan | None = None,
    ) -> None:
        identity = str(attrs.get(ATTR_PARTICIPANT_IDENTITY, "")).strip()
        if identity:
            state.user_id = identity
            if span is not None:
                self._set(span, ATTR_PARTICIPANT_CHANNEL_IDENTITY, identity)
                self._set(span, ATTR_SESSION_USER_ID, identity)
            self._sync_user_id_to_session(state)

    def _record_user_turn(
        self,
        span: ReadableSpan,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue],
        *,
        transcript: str,
        modality: str,
    ) -> None:
        self._capture_user_id(state, attrs, span=span)
        state.turn_count += 1
        self._set(span, ATTR_TURN_USER_TEXT, transcript)
        self._set(span, ATTR_TURN_INDEX, state.turn_count)
        self._set(span, ATTR_TURN_INPUT_MODALITY, modality)
        agent_hint = str(
            attrs.get(ATTR_LK_AGENT_LABEL) or attrs.get(ATTR_LK_AGENT_NAME) or ""
        )
        participant_id, diarization_source = self._resolve_user_participant(
            attrs, modality
        )
        self._emit_turn_trace(
            state,
            turn_index=state.turn_count,
            role="user",
            participant_id=participant_id,
            diarization_source=diarization_source,
            input_modality=modality,
            agent_hint=agent_hint,
            source_span=span,
        )
        state.open_agent_turn_index = state.turn_count + 1

        if self._capture_content:
            self._add_event(
                span,
                EVENT_GEN_AI_USER_MESSAGE,
                {"content": transcript},
            )

    def _stamp_events_user_text(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
        if self._turn_source != "events":
            return
        attrs = span.attributes or {}
        turn_index_raw = attrs.get(ATTR_TURN_INDEX)
        if turn_index_raw is None:
            active = self._active_turn_index(state, span.name)
            if active is None:
                return
            resolved_turn_index = active
            self._set(span, ATTR_TURN_INDEX, active)
        else:
            resolved_turn_index = _attr_int(attrs, ATTR_TURN_INDEX)
        text = state.user_text_by_turn.get(resolved_turn_index, "")
        if not text:
            return
        self._set(span, ATTR_TURN_USER_TEXT, text)
        if self._capture_content:
            self._add_event(
                span,
                EVENT_GEN_AI_USER_MESSAGE,
                {"content": text},
            )

    def _enrich_user_turn(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        confidence = _optional_float(attrs.get(ATTR_TRANSCRIPT_CONFIDENCE))
        if confidence is not None:
            self._set(span, ATTR_VOICE_STT_CONFIDENCE, confidence)

        if self._turn_source == "events":
            self._capture_user_id(state, attrs, span=span)
            self._stamp_events_user_text(span, state)
            return

        if attrs.get(ATTR_LK_IS_INTERRUPTION):
            return

        transcript = str(
            attrs.get(ATTR_LK_USER_TRANSCRIPT) or attrs.get(ATTR_LK_USER_INPUT) or ""
        ).strip()
        if not transcript:
            return

        self._record_user_turn(
            span,
            state,
            attrs,
            transcript=transcript,
            modality=self._user_turn_modality(attrs),
        )

    def _enrich_agent_turn(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        self._stamp_agent_identity(span, state, attrs)

        if self._turn_source == "events":
            self._stamp_agent_turn_timing_attrs(span, attrs)
            if attrs.get(ATTR_LK_INTERRUPTED):
                self._set(span, ATTR_TURN_INTERRUPTED, True)
            turn_index_raw = (span.attributes or {}).get(ATTR_TURN_INDEX)
            if turn_index_raw is None:
                resolved_turn_index = state.open_agent_turn_index or (state.turn_count + 1)
            else:
                resolved_turn_index = _attr_int(span.attributes or {}, ATTR_TURN_INDEX)
            agent_text = state.agent_text_by_turn.get(resolved_turn_index, "")
            if agent_text:
                self._set(span, ATTR_TURN_AGENT_TEXT, agent_text)
            return

        if state.open_agent_turn_index is None:
            transcript = str(
                attrs.get(ATTR_LK_USER_TRANSCRIPT)
                or attrs.get(ATTR_LK_USER_INPUT)
                or ""
            ).strip()
            if transcript and not attrs.get(ATTR_LK_IS_INTERRUPTION):
                self._record_user_turn(
                    span,
                    state,
                    attrs,
                    transcript=transcript,
                    modality=self._user_turn_modality(attrs),
                )

        turn_index = state.open_agent_turn_index or (state.turn_count + 1)
        self._set(span, ATTR_TURN_INDEX, turn_index)
        speech_id = str(attrs.get(ATTR_LK_SPEECH_ID, "") or "").strip()
        if speech_id:
            state.active_speech_id = speech_id
        agent_id = self._active_agent_id(state, attrs)
        agent_modality = self._user_turn_modality(attrs)
        self._emit_turn_trace(
            state,
            turn_index=turn_index,
            role="agent",
            participant_id=agent_id,
            label=agent_id,
            diarization_source=ATTR_DIAR_SOURCE_AGENT_ID,
            input_modality=agent_modality,
            agent_hint=agent_id,
            source_span=span if agent_modality == "voice" else None,
        )
        state.turn_count = turn_index
        state.open_agent_turn_index = None

        self._stamp_agent_turn_timing_attrs(span, attrs)

        if attrs.get(ATTR_LK_INTERRUPTED):
            self._set(span, ATTR_TURN_INTERRUPTED, True)

        response_text = str(attrs.get(ATTR_LK_RESPONSE_TEXT, "")).strip()
        if response_text:
            self._set(span, ATTR_TURN_AGENT_TEXT, response_text)

        if self._metrics and state.parlot_session_id:
            self._metrics.record_turn(
                state,
                e2e_latency_s=_optional_float(attrs.get(ATTR_LK_E2E_LATENCY)),
                llm_ttft_s=_optional_float(attrs.get(ATTR_LK_RESPONSE_TTFT)),
                tts_ttfb_s=state.pending_tts_ttfb_s,
                transcription_delay_s=_optional_float(
                    attrs.get(ATTR_TRANSCRIPTION_DELAY)
                ),
                eou_delay_s=_optional_float(attrs.get(ATTR_END_OF_TURN_DELAY)),
                interrupted=bool(attrs.get(ATTR_LK_INTERRUPTED)),
                participant_role="agent",
            )
            state.pending_tts_ttfb_s = None

        if self._capture_content:
            user_input = attrs.get(ATTR_LK_USER_INPUT, "")
            if user_input:
                self._add_event(
                    span,
                    EVENT_GEN_AI_USER_MESSAGE,
                    {"content": str(user_input)},
                )
            response = attrs.get(ATTR_LK_RESPONSE_TEXT, "")
            if response:
                self._add_event(
                    span,
                    EVENT_GEN_AI_ASSISTANT_MESSAGE,
                    {"content": str(response)},
                )

    def _stamp_agent_turn_timing_attrs(
        self, span: ReadableSpan, attrs: Mapping[str, AttributeValue]
    ) -> None:
        e2e = _optional_float(attrs.get(ATTR_LK_E2E_LATENCY))
        if e2e is not None:
            self._set(span, ATTR_TURN_E2E_LATENCY_S, e2e)
        ttft = _optional_float(attrs.get(ATTR_LK_RESPONSE_TTFT))
        if ttft is not None:
            self._set(span, ATTR_TURN_LLM_TTFT_S, ttft)
        transcription_delay = _optional_float(attrs.get(ATTR_TRANSCRIPTION_DELAY))
        if transcription_delay is not None:
            self._set(span, ATTR_TURN_TRANSCRIPTION_DELAY_S, transcription_delay)
        eou_delay = _optional_float(attrs.get(ATTR_END_OF_TURN_DELAY))
        if eou_delay is not None:
            self._set(span, ATTR_TURN_EOU_DELAY_S, eou_delay)

    def _enrich_drain(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        """Lifecycle drain only — not a conversational turn boundary."""
        self._stamp_agent_identity(span, state)

    def _enrich_eou(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "end_of_utterance_detection")
        lang = str(attrs.get(ATTR_EOU_LANGUAGE, "")).strip()
        if lang:
            state.languages_seen.add(lang)
            self._set(span, ATTR_VOICE_EOU_LANGUAGE, lang)
        self._stamp_events_user_text(span, state)

    def _enrich_amd(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        self._set(span, ATTR_AGENT_ROLE, "amd")
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "classify_contact")

        category = str(attrs.get(ATTR_AMD_CATEGORY, "")).strip().lower()
        if category:
            self._set(span, ATTR_VOICE_AMD_CATEGORY, category)
        amd = _AMD_CATEGORY_TO_CONTACT_TYPE.get(category, "unknown")
        self._set(span, ATTR_SESSION_AMD, amd)
        state.amd = amd

        self._stamp_agent_identity(span, state, attrs)

        if state.turn_count == 0 and state.open_agent_turn_index is None:
            self._set(span, ATTR_TURN_INDEX, 0)

    def _enrich_handoff(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        source = attrs.get(ATTR_AGENT_TRANSFER_FROM)
        target = attrs.get(ATTR_AGENT_TRANSFER_TO)
        if target is not None:
            self._stamp_agent_identity(span, state, attrs, label_override=str(target))
            target_str = str(target)
            state.agent_label = target_str
            if not state.agent_chain or state.agent_chain[-1] != target_str:
                state.agent_chain.append(target_str)
        else:
            self._stamp_agent_identity(span, state, attrs)

        if source is not None or target is not None:
            if self._turn_source != "events":
                state.handoff_count += 1
                self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)
            elif state.handoff_count:
                self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)

        state.pending_handoff_end_ns = span.end_time or time.time_ns()

    def _stamp_session_turn_attrs(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
        if state.parlot_session_id:
            self._set(span, ATTR_SESSION_ID, state.parlot_session_id)
            self._set(span, ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
            self._set(span, ATTR_GEN_AI_CONVERSATION_ID, state.conversation_id)
        active = self._active_turn_index(state, span.name)
        if active is not None:
            self._set(span, ATTR_TURN_INDEX, active)

    @staticmethod
    def _user_turn_modality(attrs: Mapping[str, AttributeValue]) -> str:
        """``voice`` when STT produced a transcript; ``text`` for typed/console input."""
        if str(attrs.get(ATTR_LK_USER_TRANSCRIPT, "")).strip():
            return "voice"
        return "text"

    @staticmethod
    def _user_turn_diarization_source(modality: str) -> str:
        return ATTR_DIAR_SOURCE_VAD if modality == "voice" else ATTR_DIAR_SOURCE_TEXT_INPUT

    @staticmethod
    def _resolve_user_participant(
        attrs: Mapping[str, AttributeValue], modality: str
    ) -> tuple[str, str]:
        for key in (ATTR_STT_SPEAKER_ID,):
            speaker = str(attrs.get(key, "")).strip()
            if speaker:
                return speaker, ATTR_DIAR_SOURCE_STT_SPEAKER_ID
        return (
            ATTR_TURN_PARTICIPANT_ID_CALLER,
            LiveKitGenAIProcessor._user_turn_diarization_source(modality),
        )

    @staticmethod
    def _speech_wall_ms_from_span(span: ReadableSpan) -> tuple[int, int] | None:
        """Wall-clock epoch ms from OTLP span bounds (LiveKit user_turn / agent_turn)."""
        start_ns = span.start_time
        end_ns = span.end_time
        if start_ns is None or end_ns is None:
            return None
        if end_ns <= start_ns:
            return None
        return start_ns // 1_000_000, end_ns // 1_000_000

    @staticmethod
    def _media_segments_from_speech(
        state: _LiveKitSessionState,
        speech_start_wall_ms: int,
        speech_end_wall_ms: int,
    ) -> tuple[int, int]:
        anchor = state.recording_anchor_wall_ms
        if anchor is None:
            return 0, 0
        return (
            max(0, speech_start_wall_ms - anchor),
            max(0, speech_end_wall_ms - anchor),
        )

    def set_recording_anchor_wall_ms(
        self, state: _LiveKitSessionState, anchor_wall_ms: int
    ) -> None:
        """Recording timeline t=0 (``audio_recording_started_at``) for media_segment_*."""
        if anchor_wall_ms <= 0:
            return
        state.recording_anchor_wall_ms = anchor_wall_ms

    def _emit_committed_user_utterance_span(
        self,
        state: _LiveKitSessionState,
        *,
        turn_index: int,
        text: str,
        modality: str,
        participant_id: str,
        diarization_source: str,
    ) -> None:
        """Events mode: export user utterance on session_agents at the user turn index."""
        if self._turn_source != "events" or not self._tracer or not state.parlot_session_id:
            return
        attrs: dict[str, AttributeValue] = {
            ATTR_SESSION_ID: state.parlot_session_id,
            ATTR_SESSION_CONVERSATION_ID: state.conversation_id,
            ATTR_GEN_AI_CONVERSATION_ID: state.conversation_id,
            ATTR_TURN_INDEX: turn_index,
            ATTR_TURN_USER_TEXT: text,
            ATTR_TURN_INPUT_MODALITY: modality,
            ATTR_AGENT_FRAMEWORK: "livekit",
            ATTR_TURN_PARTICIPANT_ID: participant_id,
            ATTR_PARTICIPANT_DIAR_SOURCE: diarization_source,
        }
        if modality == "text":
            attrs[ATTR_AGENT_ROLE] = "pipeline"
        if participant_id and participant_id != ATTR_TURN_PARTICIPANT_ID_CALLER:
            attrs[ATTR_PARTICIPANT_CHANNEL_IDENTITY] = participant_id
        if state.session_id:
            attrs[ATTR_LK_JOB_ID] = state.session_id
        if state.room_name:
            attrs[ATTR_LK_ROOM_NAME] = state.room_name
        if state.room_sid:
            attrs[ATTR_LK_ROOM_SID] = state.room_sid

        span = self._tracer.start_span("user_turn", attributes=attrs)
        stamp_livekit_platform_refs(
            span,
            job_id=state.session_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )
        if self._capture_content:
            self._add_event(span, EVENT_GEN_AI_USER_MESSAGE, {"content": text})
        span.end()

    def _emit_turn_trace(
        self,
        state: _LiveKitSessionState,
        *,
        turn_index: int,
        role: str,
        participant_id: str,
        label: str = "",
        diarization_source: str = "",
        input_modality: str = "",
        agent_hint: str = "",
        source_span: ReadableSpan | None = None,
        turn_metrics: dict[str, float] | None = None,
        interrupted: bool = False,
    ) -> None:
        if not self._tracer or not state.parlot_session_id:
            return
        active_agent_id = agent_hint or state.agent_label or "unknown"
        prev = state.last_turn_trace_id

        speech_wall: tuple[int, int] | None = None
        start_time_unix_ns: int | None = None
        end_time_unix_ns: int | None = None
        if source_span is not None and input_modality == "voice":
            speech_wall = self._speech_wall_ms_from_span(source_span)
            if speech_wall is not None:
                start_time_unix_ns = source_span.start_time
                end_time_unix_ns = source_span.end_time

        media_start_ms = 0
        media_end_ms = 0
        speech_start_wall_ms: int | None = None
        speech_end_wall_ms: int | None = None
        if speech_wall is not None:
            speech_start_wall_ms, speech_end_wall_ms = speech_wall
            media_start_ms, media_end_ms = self._media_segments_from_speech(
                state, speech_start_wall_ms, speech_end_wall_ms
            )

        metrics = turn_metrics or {}
        if speech_wall is None and input_modality == "voice":
            started = metrics.get("started_speaking_at")
            stopped = metrics.get("stopped_speaking_at")
            if started is not None and stopped is not None:
                try:
                    speech_start_wall_ms = int(float(started) * 1000)
                    speech_end_wall_ms = int(float(stopped) * 1000)
                    if speech_end_wall_ms > speech_start_wall_ms:
                        speech_wall = (speech_start_wall_ms, speech_end_wall_ms)
                        start_time_unix_ns = speech_start_wall_ms * 1_000_000
                        end_time_unix_ns = speech_end_wall_ms * 1_000_000
                        media_start_ms, media_end_ms = self._media_segments_from_speech(
                            state, speech_start_wall_ms, speech_end_wall_ms
                        )
                except (TypeError, ValueError):
                    pass

        trace_id, root_span_id = emit_turn_root_span(
            self._tracer,
            session_id=state.parlot_session_id,
            conversation_id=state.conversation_id,
            turn_index=turn_index,
            prev_trace_id=prev,
            participant_role=role,
            participant_id=participant_id,
            participant_label=label,
            diarization_source=diarization_source,
            input_modality=input_modality,
            active_agent_id=active_agent_id,
            speech_start_wall_ms=speech_start_wall_ms,
            speech_end_wall_ms=speech_end_wall_ms,
            media_segment_start_ms=media_start_ms,
            media_segment_end_ms=media_end_ms,
            start_time_unix_ns=start_time_unix_ns,
            end_time_unix_ns=end_time_unix_ns,
            e2e_latency_s=metrics.get("e2e_latency"),
            llm_ttft_s=metrics.get("llm_ttft"),
            tts_ttfb_s=metrics.get("tts_ttfb"),
            transcription_delay_s=metrics.get("transcription_delay"),
            eou_delay_s=metrics.get("eou_delay"),
            interrupted=interrupted,
        )
        state.last_turn_trace_id = trace_id
        state.turn_trace_by_index[turn_index] = trace_id
        state.turn_root_span_by_index[turn_index] = root_span_id
        self._turn_trace_registry.setdefault(state.parlot_session_id, {})[
            turn_index
        ] = (trace_id, root_span_id)

    def _apply_root_to_live_span(
        self, session_span: Any, state: _LiveKitSessionState
    ) -> None:
        """Stamp session aggregates on the live ``conversation.session`` span."""
        if session_span is None or not hasattr(session_span, "set_attribute"):
            return
        session_span.set_attribute(ATTR_SESSION_TURN_COUNT, state.turn_count)
        session_span.set_attribute(ATTR_SESSION_TOOL_CALL_COUNT, state.tool_call_count)
        session_span.set_attribute(ATTR_SESSION_HANDOFF_COUNT, state.handoff_count)
        session_span.set_attribute(
            ATTR_SESSION_TOTAL_INPUT_TOKENS, state.total_input_tokens
        )
        session_span.set_attribute(
            ATTR_SESSION_TOTAL_OUTPUT_TOKENS, state.total_output_tokens
        )
        if state.user_id:
            session_span.set_attribute(ATTR_SESSION_USER_ID, state.user_id)
        if state.agent_chain:
            chain = " → ".join(state.agent_chain)
            session_span.set_attribute(ATTR_SESSION_AGENT_CHAIN, chain)
        if state.amd:
            session_span.set_attribute(ATTR_SESSION_AMD, state.amd)
        if state.recording_anchor_wall_ms is not None:
            session_span.set_attribute(
                ATTR_SESSION_RECORDING_ANCHOR_WALL_MS,
                state.recording_anchor_wall_ms,
            )
        if state.languages_seen:
            session_span.set_attribute(
                ATTR_SESSION_LANGUAGES,
                json.dumps(sorted(state.languages_seen)),
            )
        if state.session_id:
            stamp_livekit_platform_refs(
                session_span,
                job_id=state.session_id,
                room_name=state.room_name,
                room_sid=state.room_sid,
            )
        if self._metrics and state.parlot_session_id:
            self._metrics.record_session_close(state)


def _attr_int(
    attrs: Mapping[str, AttributeValue], key: str, default: int = 0
) -> int:
    val = attrs.get(key, default)
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            return default
    return default


def _optional_float(value: AttributeValue | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _provider_to_system(provider: str) -> str:
    mapping = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gcp.vertex_ai",
        "gemini": "gcp.vertex_ai",
        "deepgram": "deepgram",
        "elevenlabs": "elevenlabs",
        "cartesia": "cartesia",
        "assemblyai": "assemblyai",
        "azure": "azure",
        "silero": "silero",
    }
    p = provider.lower()
    for key, val in mapping.items():
        if key in p:
            return val
    return ""


def _extract_new_agent(tool_output: str) -> str:
    import re

    m = re.search(r"AgentHandoff\(agent=<(\w+)", tool_output)
    return m.group(1) if m else ""


def _coerce_str_sequence(value: AttributeValue | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [text]
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v is not None and str(v).strip()]
        return [text]
    return [str(value)]


def _preview_from_chat_ctx(raw: str) -> tuple[str, str]:
    """Return (last_user_text, last_assistant_or_tool_output) from lk.chat_ctx JSON."""
    if not raw:
        return "", ""
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return "", ""
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return "", ""

    last_user = ""
    last_out = ""
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "message":
            role = item.get("role")
            content = item.get("content")
            text = ""
            if isinstance(content, list):
                text = " ".join(str(c) for c in content if c)
            elif content:
                text = str(content)
            if role == "user" and text:
                last_user = text
            elif role == "assistant" and text:
                last_out = text
        elif kind == "function_call_output":
            out = item.get("output", "")
            if out:
                last_out = str(out)
    return last_user, last_out
