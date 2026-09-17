"""
LiveKitGenAIProcessor — enriches LiveKit Agents OTel spans in-place.

Turn boundaries (livekit-agents 1.7.0): ``user_turn`` and ``agent_turn``.
``eou_detection`` is a child model span; ``drain_agent_activity`` is lifecycle only.
Content-bearing ``lk.pii.*`` attrs are accepted alongside legacy ``lk.*`` keys.

Enrichment logic lives in collaborator modules; this class is the thin dispatcher.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, FrozenSet, Optional

if TYPE_CHECKING:
    from parlot.core.context import ParlotContext

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Status, StatusCode, Tracer
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_STAGE,
    ATTR_EXCEPTION_TYPE,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_RESPONSE_MODEL,
    ATTR_GEN_AI_SYSTEM,
    ATTR_PARLOT_SPAN_KIND,
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
    ATTR_TURN_INDEX,
    PARLOT_SPAN_KIND_EVALUATION,
    SPAN_AGENT_HANDOFF,
    SPAN_CONVERSATION_SESSION,
    SPAN_PARLOT_SESSION_CLOSE,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_AGENT_NAME,
    ATTR_LK_FNC_TOOL_ERROR,
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
    ATTR_LK_SPEECH_ID,
    ATTR_ROOM_NAME_LEGACY,
    METADATA_JOB_ID,
    METADATA_ROOM_ID,
    attr_get,
)
from ._span_rename import (
    NATIVE_TURN_SPANS,
    apply_livekit_span_rename,
    remap_livekit_span_name,
)
from ._span_stage import livekit_agent_role_for_span, livekit_agent_stage_for_span
from ._platform_refs import lookup_room_context, stamp_livekit_platform_refs
from ._agent_identity import (
    append_agent_chain_step,
    ensure_agent_chain_seeded,
    stamp_session_agent_identity,
    topology_agent_name,
)
from ._auto import configured_agent_id, configured_agent_version, explicit_agent_id
from ._session import (
    get_job_bootstrap,
    get_sticky_closed_session,
    handle_conversation_session_on_end,
)
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.sdk_version import stamp_session_sdk_version
from ._session_state import _LiveKitSessionState
from ._span_util import provider_to_system
from ._handoff_tracker import HandoffTracker
from ._token_aggregator import TokenAggregator
from ._recording_coordinator import RecordingCoordinator
from ._turn_enricher import TurnEnricher, _AGENT_PIPELINE_SPANS

logger = logging.getLogger("parlot.instrumentation.livekit")

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


class LiveKitGenAIProcessor(ParlotBaseProcessor):
    """Enriches LiveKit Agent spans in-place with Parlot conventions.

    Intercepts spans from the LiveKit Agents SDK and normalizes them into
    Parlot's three-layer semantic vocabulary:

    1. **Conversation Contract** — session start/close, turns, agent handoffs.
    2. **OTel GenAI (v1.41.0)** — LLM inference, tool executions, workflows.
    3. **Voice spans** — TTS, STT, and end-of-utterance operational timings.
    """

    def __init__(
        self,
        capture_genai_content: Optional[bool] = None,
        handoff_tool_names: Optional[set[str]] = None,
        *,
        context: Optional["ParlotContext"] = None,
    ) -> None:
        from parlot.core.context import ParlotContext

        # Explicit override for tests / rare call sites; None → policy at emit time.
        self._capture_genai_content_override = capture_genai_content
        self._handoff_tools = handoff_tool_names or set()
        self._context = context if context is not None else ParlotContext()
        self._sessions: dict[str, _LiveKitSessionState] = {}
        self._turn_trace_registry: dict[str, dict[int, tuple[str, str]]] = {}
        self._tracer: Tracer | None = None
        self._metrics = None
        self._turn_source: str = "spans"

        self._handoff = HandoffTracker(
            set_attr=self._set,
            handoff_tools=self._handoff_tools,
        )
        self._tokens = TokenAggregator(
            set_attr=self._set,
            plugin_host=self,
        )
        self._recording = RecordingCoordinator(
            get_capture_override=lambda: self._capture_genai_content_override,
            active_agent_id_fn=self._active_agent_id,
            get_context=lambda: self._context,
        )
        self._turns = TurnEnricher(
            set_attr=self._set,
            add_event=self._add_event,
            maybe_update=self._maybe_update,
            get_turn_source=lambda: self._turn_source,
            get_tracer=lambda: self._tracer,
            get_metrics=lambda: self._metrics,
            genai_content_enabled=self._recording.genai_content_enabled,
            active_agent_id=self._active_agent_id,
            stamp_agent_identity=self._stamp_agent_identity,
            stamp_response_model_if_distinct=self._stamp_response_model_if_distinct,
            handoff_tracker=self._handoff,
            token_aggregator=self._tokens,
            recording=self._recording,
            turn_trace_registry=self._turn_trace_registry,
        )

    def on_start(self, span, parent_context=None) -> None:
        super().on_start(span, parent_context)
        # Capture turn.index while open_agent_turn_index is still set — child
        # llm/tts spans often end after conversation_item_added clears it.
        bootstrap = get_job_bootstrap()
        if bootstrap is None or not bootstrap.state.parlot_session_id:
            return
        self._turns.stamp_turn_index_at_start(span, bootstrap.state)

    def on_end(self, span: ReadableSpan) -> None:
        super().on_end(span)
        try:
            name = span.name
            if name == SPAN_CONVERSATION_SESSION:
                handle_conversation_session_on_end()
                return
            self._enrich(span)
            self._log_compare_span(span)
        except Exception as exc:
            logger.error(
                "parlot: LiveKitGenAIProcessor failed on span %r — %s",
                span.name,
                exc,
            )
            logger.debug(
                "parlot: LiveKitGenAIProcessor failed on span %r",
                span.name,
                exc_info=True,
            )

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
        """Deferred enrichment, turn-attr copy, then GenAI/voice rename for export."""
        self._turns.correct_function_tool_timing(spans)

        llm_spans = sorted(
            (s for s in spans if s.name == "llm_node"),
            key=lambda s: s.end_time or 0,
        )
        for span in llm_spans:
            # FIFO token attach before stamping active_speech_id (which would
            # pin every span to the latest speech and break multi-node batches).
            self._tokens.apply_plugin_llm_usage_to_span(
                span, dict(span.attributes or {}), prefer_fifo=True
            )
            attrs = span.attributes or {}
            if not attrs.get(ATTR_LK_SPEECH_ID):
                bootstrap = get_job_bootstrap()
                speech_id = ""
                if bootstrap is not None:
                    speech_id = bootstrap.state.active_speech_id.strip()
                if speech_id:
                    self._set(span, ATTR_LK_SPEECH_ID, speech_id)

        self._turns.merge_native_turn_attrs_onto_parlot_turns(spans)

        from ._telemetry_compare import compare_enabled, get_compare_logger

        if compare_enabled():
            bootstrap = get_job_bootstrap()
            if bootstrap is not None and bootstrap.state.parlot_session_id:
                session_id = bootstrap.state.parlot_session_id
                for span in spans:
                    if span.name == "llm_node":
                        get_compare_logger().accumulate_export_tokens(
                            session_id,
                            span_name=span.name or "",
                            attrs=dict(span.attributes or {}),
                        )

        # Rename LiveKit-native ops → GenAI/voice names before export filter.
        for span in spans:
            native = span.name or ""
            if native in NATIVE_TURN_SPANS:
                # Dropped by export filter (remap returns None); attrs already merged.
                continue
            if remap_livekit_span_name(native, span.attributes or {}) is not None:
                apply_livekit_span_rename(span)
                role = livekit_agent_role_for_span(span.name or "")
                if role and not (span.attributes or {}).get(ATTR_AGENT_ROLE):
                    self._set(span, ATTR_AGENT_ROLE, role)

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

    # ------------------------------------------------------------------
    # Public facades (called by _events / _egress)
    # ------------------------------------------------------------------

    def mark_conversation_item_committed(self, item_id: str) -> bool:
        return self._turns.mark_conversation_item_committed(item_id)

    def mark_handoff_item_committed(self, item_id: str) -> None:
        self._handoff.mark_handoff_item_committed(item_id)

    def committed_handoff_item_ids(self) -> set[str]:
        return self._handoff.committed_handoff_item_ids()

    def record_handoff_from_event(
        self, *, from_agent: str = "", to_agent: str = ""
    ) -> None:
        self._handoff.record_handoff_from_event(
            from_agent=from_agent, to_agent=to_agent
        )

    def note_user_transcription_meta(
        self, *, speaker_id: str = "", language: str = ""
    ) -> None:
        self._turns.note_user_transcription_meta(
            speaker_id=speaker_id, language=language
        )

    def note_function_tools_executed(self, count: int) -> None:
        self._turns.note_function_tools_executed(count)

    def apply_session_usage(self, total_in: int, total_out: int) -> None:
        self._tokens.apply_session_usage(total_in, total_out)

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
        self._turns.commit_user_message(
            text, interrupted=interrupted, metrics=metrics
        )

    def commit_agent_message(
        self,
        text: str,
        *,
        interrupted: bool = False,
        metrics: dict[str, float] | None = None,
    ) -> None:
        self._turns.commit_agent_message(
            text, interrupted=interrupted, metrics=metrics
        )

    def lookup_turn_trace(
        self, session_id: str, turn_index: int
    ) -> tuple[str, str] | None:
        return self._turns.lookup_turn_trace(session_id, turn_index)

    def set_recording_anchor_wall_ms(
        self, state: _LiveKitSessionState, anchor_wall_ms: int
    ) -> None:
        self._recording.set_recording_anchor_wall_ms(state, anchor_wall_ms)

    def _apply_plugin_llm_usage_to_span(
        self,
        span: ReadableSpan,
        attrs: Mapping[str, AttributeValue],
        *,
        prefer_fifo: bool = False,
    ) -> None:
        self._tokens.apply_plugin_llm_usage_to_span(
            span, attrs, prefer_fifo=prefer_fifo
        )

    # ------------------------------------------------------------------
    # Session / agent identity helpers (kept on processor)
    # ------------------------------------------------------------------

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
        raw_label = attrs.get(ATTR_LK_AGENT_LABEL)
        raw_name = attrs.get(ATTR_LK_AGENT_NAME)
        label_str = raw_label if isinstance(raw_label, str) else None
        name_str = raw_name if isinstance(raw_name, str) else None
        label = topology_agent_name(label_str) or topology_agent_name(name_str)
        if label:
            self._maybe_update(state, "agent_label", label)
            canonical = explicit_agent_id()
            if label != canonical:
                append_agent_chain_step(state, label)

    def _active_agent_id(
        self,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue],
        *,
        label_override: str | None = None,
    ) -> str:
        if label_override:
            override = topology_agent_name(label_override)
            if override:
                return override
        # Prefer sub-agent labels over worker name; never use LiveKit AD_* dispatch ids.
        for candidate in (
            attrs.get(ATTR_LK_AGENT_LABEL),
            state.agent_label,
            attrs.get(ATTR_LK_AGENT_NAME),
            state.worker_agent_name,
            explicit_agent_id(),
            state.agent_chain[-1] if state.agent_chain else "",
        ):
            cand_str = candidate if isinstance(candidate, str) else None
            name = topology_agent_name(cand_str)
            if name:
                return name
        return "unknown"

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
        if not resolved.get(ATTR_GEN_AI_AGENT_NAME):
            agent_id = self._active_agent_id(
                state, resolved, label_override=label_override
            )
            if agent_id == "unknown":
                agent_id = configured_agent_id() or "unknown"
            if agent_id != "unknown":
                self._set(span, ATTR_GEN_AI_AGENT_NAME, agent_id)
        version = configured_agent_version()
        if version and not resolved.get(ATTR_GEN_AI_AGENT_VERSION):
            self._set(span, ATTR_GEN_AI_AGENT_VERSION, version)

    def _stamp_response_model_if_distinct(
        self,
        span: ReadableSpan,
        attrs: Mapping[str, AttributeValue],
    ) -> None:
        response_model = str(attrs.get(ATTR_GEN_AI_RESPONSE_MODEL, "") or "").strip()
        if not response_model:
            return
        request_model = str(attrs.get(ATTR_GEN_AI_MODEL, "") or "").strip()
        if request_model and response_model == request_model:
            return
        self._set(span, ATTR_GEN_AI_RESPONSE_MODEL, response_model)

    def _stamp_session_turn_attrs(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
        if state.parlot_session_id:
            self._set(span, ATTR_SESSION_ID, state.parlot_session_id)
            self._set(span, ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
            self._set(span, ATTR_GEN_AI_CONVERSATION_ID, state.conversation_id)
        if (span.attributes or {}).get(ATTR_TURN_INDEX) is not None:
            return
        active = self._turns.active_turn_index(state, span.name)
        if active is not None:
            self._set(span, ATTR_TURN_INDEX, active)

    def _stamp_error_status_if_needed(self, span: ReadableSpan) -> None:
        """Normalize failed pipeline spans to OTel ERROR status for OTLP export."""
        attrs = span.attributes or {}
        if attrs.get(ATTR_EXCEPTION_TYPE) or attrs.get(ATTR_LK_FNC_TOOL_ERROR):
            span._status = Status(StatusCode.ERROR)

    # ------------------------------------------------------------------
    # Enrichment dispatcher
    # ------------------------------------------------------------------

    def _enrich(self, span: ReadableSpan) -> None:
        name = span.name
        if name in ("parlot.turn", SPAN_PARLOT_SESSION_CLOSE, SPAN_CONVERSATION_SESSION):
            return
        attrs = span.attributes or {}
        state = self._resolve_session_state(span, attrs)
        if state is None:
            # Post-close JudgeGroup LLM: sticky closed session only — no aggregates.
            if name in ("llm_request", "llm_request_run", "llm_node"):
                self._enrich_late_evaluation_llm(span, attrs)
            return

        explicit_job = attrs.get(ATTR_LK_JOB_ID) or attrs.get(METADATA_JOB_ID)
        if explicit_job:
            self._maybe_update(state, "session_id", explicit_job)
        self._maybe_update(
            state,
            "room_name",
            attr_get(attrs, ATTR_LK_ROOM_NAME, ATTR_ROOM_NAME_LEGACY),
        )
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
        if stage and not (span.attributes or {}).get(ATTR_AGENT_STAGE):
            self._set(span, ATTR_AGENT_STAGE, stage)

        if name in ("llm_request", "llm_request_run"):
            self._enrich_llm_request(span, state)
        elif name == "llm_node":
            self._turns.enrich_llm_node(span, state)
        elif name == "tts_node":
            self._turns.enrich_tts_node(span, state)
        elif name == "tts_request_run":
            self._turns.enrich_tts_request(span, state)
        elif name == "function_tool":
            self._turns.enrich_function_tool(span, state)
        elif name == "user_turn":
            self._turns.enrich_user_turn(span, state)
        elif name == "agent_turn":
            self._turns.enrich_agent_turn(span, state)
        elif name == "drain_agent_activity":
            self._turns.enrich_drain(span, state)
        elif name == "eou_detection":
            self._turns.enrich_eou(span, state)
        elif name == "amd":
            self._turns.enrich_amd(span, state)
        elif name == SPAN_AGENT_HANDOFF:
            self._handoff.enrich_handoff(
                span,
                state,
                stamp_agent_identity=self._stamp_agent_identity,
                turn_source=self._turn_source,
            )

        if name in _AGENT_PIPELINE_SPANS:
            self._stamp_error_status_if_needed(span)

    def _enrich_late_evaluation_llm(
        self,
        span: ReadableSpan,
        attrs: Mapping[str, AttributeValue],
    ) -> None:
        """Stamp closed-session ids + evaluation attrs; do not mutate turn/token state."""
        job_id = attrs.get(ATTR_LK_JOB_ID) or attrs.get(METADATA_JOB_ID)
        if not job_id:
            try:
                from livekit.agents.job import get_job_context

                ctx = get_job_context()
                if ctx is not None:
                    job_id = str(ctx.job.id)
            except Exception:
                job_id = None
        if not job_id:
            return
        sticky = get_sticky_closed_session(str(job_id))
        if sticky is None:
            return
        self._set(span, ATTR_SESSION_ID, sticky.session_id)
        self._set(span, ATTR_SESSION_CONVERSATION_ID, sticky.conversation_id)
        self._set(span, ATTR_GEN_AI_CONVERSATION_ID, sticky.conversation_id)
        self._set(span, ATTR_LK_JOB_ID, str(job_id))
        self._set(span, ATTR_AGENT_FRAMEWORK, "livekit")
        # Evaluation is a Parlot Layer-3 signal (parlot.span.kind), not a GenAI op.
        self._set(span, ATTR_PARLOT_SPAN_KIND, PARLOT_SPAN_KIND_EVALUATION)
        stage = livekit_agent_stage_for_span(span.name or "")
        if stage and not attrs.get(ATTR_AGENT_STAGE):
            self._set(span, ATTR_AGENT_STAGE, stage)
        self._stamp_error_status_if_needed(span)

    def _enrich_llm_request(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
        attrs = span.attributes or {}
        self._stamp_agent_identity(span, state, attrs)

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        self._tokens.accumulate_llm_request_tokens(span, state, attrs)
        self._handoff.stamp_transfer_latency_if_pending(span, state)
        self._stamp_response_model_if_distinct(span, span.attributes or attrs)

    def _apply_root_to_live_span(
        self, session_span: Any, state: _LiveKitSessionState
    ) -> None:
        """Stamp session aggregates on the live ``parlot.session`` span."""
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
        ensure_agent_chain_seeded(state)
        for agent in state.agent_chain:
            state.topology.push_agent_chain(agent)
        state.topology.stamp_session_span(session_span, final_turn=state.turn_count)
        stamp_session_agent_identity(session_span, state)
        stamp_session_sdk_version(session_span)
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
