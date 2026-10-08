"""Turn / tool / pipeline enrichment for LiveKit GenAI spans."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any, FrozenSet, Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Tracer
from opentelemetry.util.types import AttributeValue

from parlot.core.language import detect_language_from_text
from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_AGENT_INSTRUCTIONS_EXCERPT,
    ATTR_AGENT_STATIC_INSTRUCTIONS_EXCERPT,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_STAGE,
    ATTR_AGENT_TOOL_CALL_INDEX,
    ATTR_AGENT_TOOL_IS_ERROR,
    ATTR_AGENT_TOOL_NAME,
    ATTR_AGENT_TOOL_NAMES,
    ATTR_AGENT_TOOL_TIMING_CORRECTED,
    ATTR_DIAR_SOURCE_AGENT_ID,
    ATTR_DIAR_SOURCE_STT_SPEAKER_ID,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_TOOL_DURATION_MS,
    ATTR_GEN_AI_TTS_TTFB_S,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_TOOL_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
    ATTR_SESSION_AMD,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_SESSION_USER_ID,
    ATTR_STT_SPEAKER_ID,
    ATTR_TURN_PARTICIPANT_ID_CALLER,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_E2E_LATENCY_S,
    ATTR_TURN_EOU_DELAY_S,
    ATTR_TURN_INDEX,
    ATTR_TURN_LLM_TTFT_S,
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_SPEECH_WALL_END_MS,
    ATTR_TURN_SPEECH_WALL_START_MS,
    ATTR_TURN_TRANSCRIPTION_DELAY_S,
    ATTR_TURN_TTS_TTFB_S,
    ATTR_TURN_USER_TEXT,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_INTERRUPTED,
    ATTR_VOICE_STT_CONFIDENCE,
    ATTR_TOOL_INPUT_PAYLOAD,
    ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
    ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW,
    ATTR_PARTICIPANT_CHANNEL_IDENTITY,
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_VOICE_AMD_CATEGORY,
    ATTR_VOICE_EOU_LANGUAGE,
    SPAN_PARLOT_TURN,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_AMD_CATEGORY,
    ATTR_CHAT_CTX_LEGACY,
    ATTR_DIAR_SOURCE_REALTIME_INTERRUPT,
    ATTR_DIAR_SOURCE_TEXT_INPUT,
    ATTR_DIAR_SOURCE_VAD,
    ATTR_EOU_LANGUAGE,
    ATTR_END_OF_TURN_DELAY,
    ATTR_FUNCTION_TOOL_ARGS_LEGACY,
    ATTR_FUNCTION_TOOL_OUTPUT_LEGACY,
    ATTR_INSTRUCTIONS_LEGACY,
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
    ATTR_PARTICIPANT_IDENTITY_LEGACY,
    ATTR_RESPONSE_TEXT_LEGACY,
    ATTR_TRANSCRIPT_CONFIDENCE,
    ATTR_TRANSCRIPTION_DELAY,
    ATTR_TTS_INPUT_TEXT_LEGACY,
    ATTR_USER_INPUT_LEGACY,
    ATTR_USER_TRANSCRIPT_LEGACY,
    attr_get,
)
from ._chat_ctx import (
    full_instructions_excerpt,
    static_instructions_excerpt,
)
from ._span_rename import NATIVE_TOOL_SPANS, NATIVE_TURN_SPANS
from ._platform_refs import stamp_livekit_platform_refs
from ._agent_identity import topology_agent_name
from ._session import get_job_bootstrap
from ._session_state import _LiveKitSessionState
from ._span_util import (
    AMD_CATEGORY_TO_CONTACT_TYPE,
    _ASYNC_TOOL_MIN_DURATION_NS,
    _EXECUTION_START_GAP_NS,
    _INSTRUCTIONS_EXCERPT_CHARS,
    _MAX_TOOL_PAYLOAD_CHARS,
    _TOOL_PREVIEW_CHARS,
    attr_int,
    coerce_str_sequence,
    optional_float,
    preview_from_chat_ctx,
    provider_to_system,
)
from ._turn_traces import emit_turn_root_span
from ._handoff_tracker import HandoffTracker
from ._token_aggregator import TokenAggregator
from ._recording_coordinator import RecordingCoordinator

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

SetAttrFn = Callable[[ReadableSpan, str, AttributeValue], None]
AddEventFn = Callable[..., None]
MaybeUpdateFn = Callable[..., None]
StampAgentIdentityFn = Callable[..., None]
ActiveAgentIdFn = Callable[..., str]
StampResponseModelFn = Callable[..., None]


class TurnEnricher:
    """Owns turn commits, pipeline merge, and turn/tool/TTS/EOU/AMD enrichment."""

    def __init__(
        self,
        *,
        set_attr: SetAttrFn,
        add_event: AddEventFn,
        maybe_update: MaybeUpdateFn,
        get_turn_source: Callable[[], str],
        get_tracer: Callable[[], Tracer | None],
        get_metrics: Callable[[], Any],
        genai_content_enabled: Callable[[_LiveKitSessionState | None], bool],
        active_agent_id: ActiveAgentIdFn,
        stamp_agent_identity: StampAgentIdentityFn,
        stamp_response_model_if_distinct: StampResponseModelFn,
        handoff_tracker: HandoffTracker,
        token_aggregator: TokenAggregator,
        recording: RecordingCoordinator,
        turn_trace_registry: dict[str, dict[int, tuple[str, str]]],
    ) -> None:
        self._set = set_attr
        self._add_event = add_event
        self._maybe_update = maybe_update
        self._get_turn_source = get_turn_source
        self._get_tracer = get_tracer
        self._get_metrics = get_metrics
        self._genai_content_enabled = genai_content_enabled
        self._active_agent_id = active_agent_id
        self._stamp_agent_identity = stamp_agent_identity
        self._stamp_response_model_if_distinct = stamp_response_model_if_distinct
        self._handoff = handoff_tracker
        self._tokens = token_aggregator
        self._recording = recording
        self._turn_trace_registry = turn_trace_registry

    @property
    def _turn_source(self) -> str:
        return self._get_turn_source()

    @property
    def _tracer(self) -> Tracer | None:
        return self._get_tracer()

    @property
    def _metrics(self) -> Any:
        return self._get_metrics()

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

    def correct_function_tool_timing(self, spans: list[ReadableSpan]) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        queue = list(bootstrap.state.tool_execution_ns_queue)
        if not queue:
            return

        tool_spans = sorted(
            (
                s
                for s in spans
                if (s.name or "") in NATIVE_TOOL_SPANS
                or (s.name or "").startswith("execute_tool")
            ),
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
        user_role = self._user_turn_role(state, participant_id)
        agent_hint = topology_agent_name(state.agent_label) or topology_agent_name(
            state.worker_agent_name
        )
        event_metrics = metrics or {}
        modality = self._modality_for_user_text(text, state, event_metrics)
        turn_label = ""
        speech_wall_override: tuple[int, int] | None = None
        media_segment_override: tuple[int, int] | None = None

        if state.pending_interrupt_speech_end_wall_ms > 0:
            speech_start_wall_ms = state.pending_interrupt_speech_end_wall_ms
            stopped = event_metrics.get("stopped_speaking_at")
            if stopped is not None:
                try:
                    speech_end_wall_ms = int(float(stopped) * 1000)
                except (TypeError, ValueError):
                    speech_end_wall_ms = int(time.time() * 1000)
            else:
                speech_end_wall_ms = int(time.time() * 1000)
            if speech_end_wall_ms <= speech_start_wall_ms:
                speech_end_wall_ms = speech_start_wall_ms + 1
            speech_wall_override = (speech_start_wall_ms, speech_end_wall_ms)
            media_start_ms = state.pending_interrupt_media_end_ms
            _, media_end_ms = self._recording.media_segments_from_speech(
                state, speech_start_wall_ms, speech_end_wall_ms
            )
            media_segment_override = (media_start_ms, media_end_ms)
            modality = "voice"
            diarization_source = ATTR_DIAR_SOURCE_REALTIME_INTERRUPT
            turn_label = "Caller"
            state.pending_interrupt_media_end_ms = 0
            state.pending_interrupt_speech_end_wall_ms = 0

        state.last_user_input_modality = modality
        user_language = state.pending_user_language
        self._emit_turn_trace(
            state,
            turn_index=user_turn_index,
            role=user_role,
            participant_id=participant_id,
            label=turn_label,
            diarization_source=diarization_source,
            input_modality=modality,
            agent_hint=agent_hint,
            turn_metrics=event_metrics,
            interrupted=interrupted,
            speech_wall_override=speech_wall_override,
            media_segment_override=media_segment_override,
            language=user_language,
            utterance_text=committed_text,
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
            metrics=event_metrics,
            interrupted=interrupted,
            participant_role=user_role,
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
        modality = state.last_user_input_modality or "voice"
        self._emit_turn_trace(
            state,
            turn_index=turn_index,
            role="agent",
            participant_id=agent_id,
            label=agent_id,
            diarization_source=ATTR_DIAR_SOURCE_AGENT_ID,
            input_modality=modality,
            agent_hint=agent_id,
            turn_metrics=metrics,
            interrupted=interrupted,
            utterance_text=text.strip(),
        )
        self._emit_committed_agent_utterance_span(
            state,
            turn_index=turn_index,
            text=text.strip(),
            modality=modality,
            participant_id=agent_id,
        )
        if interrupted and metrics:
            self._stash_interrupt_boundary(state, metrics)
        self._remember_agent_speech_end(state, metrics)
        state.turn_count = turn_index
        state.open_agent_turn_index = None
        self._record_turn_metrics_from_event(
            state,
            turn_index=turn_index,
            metrics=metrics or {},
            interrupted=interrupted,
            participant_role="agent",
        )

    def lookup_turn_trace(
        self, session_id: str, turn_index: int
    ) -> tuple[str, str] | None:
        by_turn = self._turn_trace_registry.get(session_id)
        if not by_turn:
            return None
        return by_turn.get(turn_index)

    def user_turn_index_for_events(
        self, state: _LiveKitSessionState, span_name: str
    ) -> Optional[int]:
        if span_name not in _USER_TURN_SPAN_NAMES:
            return None
        if state.last_user_turn_index:
            return state.last_user_turn_index
        if state.open_agent_turn_index is not None and state.open_agent_turn_index > 1:
            return state.open_agent_turn_index - 1
        return state.turn_count if state.turn_count else None

    def active_turn_index(
        self, state: _LiveKitSessionState, span_name: str
    ) -> Optional[int]:
        """Resolve ``turn.index`` for an in-flight LiveKit span.

        Agent pipeline spans (``llm_*``, ``tts_*``, tools, ``agent_turn``, …)
        must track the *open* agent turn — the same index
        :meth:`commit_agent_message` will use. Falling back to ``turn_count``
        (last *completed* turn) dumps later TTS/LLM rows onto turn 1 after the
        greeting commits and clears ``open_agent_turn_index``.

        Prefer stamping at ``on_start`` (see :meth:`stamp_turn_index_at_start`)
        so children keep the index even if the agent message commits (and
        clears ``open_agent_turn_index``) before they end.
        """
        if span_name == "job_entrypoint":
            return None
        user_turn_index = self.user_turn_index_for_events(state, span_name)
        if user_turn_index is not None:
            return user_turn_index
        if (
            span_name in _AGENT_PIPELINE_SPANS
            and span_name not in _USER_TURN_SPAN_NAMES
        ):
            if state.open_agent_turn_index is not None:
                return state.open_agent_turn_index
            # Match commit_agent_message: next agent turn when none is open
            # (greeting, consecutive agent reply, or race before events open).
            return state.turn_count + 1
        if state.turn_count:
            return state.turn_count
        return None

    def stamp_turn_index_at_start(
        self, span: Any, state: _LiveKitSessionState
    ) -> None:
        """Stamp ``turn.index`` while the agent turn is still open.

        LiveKit ends child ``tts_node`` / ``llm_*`` spans after
        ``conversation_item_added`` may have already cleared
        ``open_agent_turn_index``. Capturing the index at start avoids the
        stale ``turn_count`` fallback on ``on_end``.
        """
        name = getattr(span, "name", None) or ""
        if name not in _AGENT_PIPELINE_SPANS or name in _USER_TURN_SPAN_NAMES:
            return
        attrs = getattr(span, "attributes", None) or {}
        if attrs.get(ATTR_TURN_INDEX) is not None:
            return
        active = self.active_turn_index(state, name)
        if active is None:
            return
        set_attr = getattr(span, "set_attribute", None)
        if callable(set_attr):
            set_attr(ATTR_TURN_INDEX, active)
        else:
            self._set(span, ATTR_TURN_INDEX, active)

    def enrich_llm_node(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        self._stamp_agent_identity(span, state, attrs)

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "chat")

        # Attach tokens using the span's own speech_id (or FIFO), before we
        # stamp active_speech_id — otherwise every node inherits the latest id.
        self._tokens.apply_plugin_llm_usage_to_span(span, dict(attrs))

        if not (span.attributes or {}).get(ATTR_LK_SPEECH_ID) and state.active_speech_id:
            self._set(span, ATTR_LK_SPEECH_ID, state.active_speech_id)

        chat_raw = str(
            attr_get(attrs, ATTR_LK_CHAT_CTX, ATTR_CHAT_CTX_LEGACY, default="") or ""
        )
        lk_instructions = str(
            attr_get(
                attrs, ATTR_LK_INSTRUCTIONS, ATTR_INSTRUCTIONS_LEGACY, default=""
            )
            or ""
        ).strip()
        full_excerpt = full_instructions_excerpt(
            chat_raw,
            lk_instructions,
            max_chars=_INSTRUCTIONS_EXCERPT_CHARS,
        )
        static_excerpt = static_instructions_excerpt(
            chat_raw,
            lk_instructions,
            max_chars=_INSTRUCTIONS_EXCERPT_CHARS,
        )
        if full_excerpt:
            self._set(span, ATTR_AGENT_INSTRUCTIONS_EXCERPT, full_excerpt)
        if static_excerpt:
            self._set(span, ATTR_AGENT_STATIC_INSTRUCTIONS_EXCERPT, static_excerpt)

        agent_id = self._active_agent_id(state, span.attributes or {})
        if static_excerpt and agent_id != "unknown":
            state.topology.record_instructions(agent_id, static_excerpt)

        tools = coerce_str_sequence(attrs.get(ATTR_LK_FUNCTION_TOOLS))
        if tools:
            self._set(span, ATTR_AGENT_TOOL_NAMES, json.dumps(tools))

        user_text, assistant_text = preview_from_chat_ctx(chat_raw)
        if user_text and self._turn_source != "events":
            self._set(span, ATTR_TURN_USER_TEXT, user_text)
        if assistant_text and self._turn_source != "events":
            self._set(span, ATTR_TURN_AGENT_TEXT, assistant_text)

        if self._genai_content_enabled(state):
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

        self._stamp_response_model_if_distinct(span, span.attributes or attrs)

    def enrich_tts_node(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "text_to_speech")

        ttfb = attrs.get(ATTR_LK_RESPONSE_TTFB)
        if isinstance(ttfb, (int, float, str)):
            try:
                ttfb_s = float(ttfb)
                self._set(span, ATTR_GEN_AI_TTS_TTFB_S, ttfb_s)
                state.pending_tts_ttfb_s = ttfb_s
            except (ValueError, TypeError):
                pass

    def enrich_tts_request(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "text_to_speech")

        if self._genai_content_enabled(state):
            text = attr_get(
                attrs, ATTR_LK_TTS_INPUT_TEXT, ATTR_TTS_INPUT_TEXT_LEGACY, default=""
            )
            if text:
                self._add_event(
                    span,
                    EVENT_GEN_AI_ASSISTANT_MESSAGE,
                    {"content": str(text), "modality": "text_for_speech"},
                )

    def enrich_function_tool(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
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
        tool_output = str(
            attr_get(
                attrs,
                ATTR_LK_FNC_TOOL_OUTPUT,
                ATTR_FUNCTION_TOOL_OUTPUT_LEGACY,
                default="",
            )
            or ""
        )
        is_error = bool(attrs.get(ATTR_LK_FNC_TOOL_ERROR, False))
        if tool_name:
            self._set(span, ATTR_AGENT_TOOL_NAME, tool_name)
        self._set(span, ATTR_AGENT_TOOL_IS_ERROR, is_error)
        duration_ms = 0.0
        if span.end_time is not None and span.start_time is not None:
            duration_ms = round((span.end_time - span.start_time) / 1_000_000, 2)

        tool_args_raw = attr_get(
            attrs,
            ATTR_LK_FNC_TOOL_ARGS,
            ATTR_FUNCTION_TOOL_ARGS_LEGACY,
            default="",
        )
        tool_args = str(tool_args_raw) if tool_args_raw else ""

        if self._genai_content_enabled(state) and tool_args:
            payload = tool_args[:_MAX_TOOL_PAYLOAD_CHARS]
            self._set(span, ATTR_TOOL_INPUT_PAYLOAD, payload)
            self._set(
                span,
                ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
                payload[:_TOOL_PREVIEW_CHARS],
            )
        if self._genai_content_enabled(state) and tool_output:
            out_preview = str(tool_output)[:_TOOL_PREVIEW_CHARS]
            self._set(span, ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW, out_preview)

        if span.end_time is not None and span.start_time is not None:
            self._set(span, ATTR_GEN_AI_TOOL_DURATION_MS, duration_ms)

        self._handoff.apply_function_tool_handoff(
            span, state, tool_name=tool_name, tool_output=tool_output
        )

        if self._genai_content_enabled(state):
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

    def enrich_user_turn(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        confidence = optional_float(attrs.get(ATTR_TRANSCRIPT_CONFIDENCE))
        if confidence is not None:
            self._set(span, ATTR_VOICE_STT_CONFIDENCE, confidence)

        if self._turn_source == "events":
            self._capture_user_id(state, attrs, span=span)
            self._stamp_events_user_text(span, state)
            turn_index = attr_int(span.attributes or {}, ATTR_TURN_INDEX) or (
                self.active_turn_index(state, "user_turn") or 0
            )
            if turn_index:
                self._set(span, ATTR_TURN_INDEX, turn_index)
            self._stash_turn_pipeline_attrs(
                state, turn_index, self._pipeline_attrs_from_user_turn(span, state)
            )
            return

        if attrs.get(ATTR_LK_IS_INTERRUPTION):
            return

        transcript = str(
            attr_get(attrs, ATTR_LK_USER_TRANSCRIPT, ATTR_USER_TRANSCRIPT_LEGACY)
            or attr_get(attrs, ATTR_LK_USER_INPUT, ATTR_USER_INPUT_LEGACY)
            or ""
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
        self._stash_turn_pipeline_attrs(
            state,
            state.turn_count,
            self._pipeline_attrs_from_user_turn(span, state),
        )

    def enrich_agent_turn(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        self._stamp_agent_identity(span, state, attrs)

        if self._turn_source == "events":
            self._stamp_agent_turn_timing_attrs(span, attrs)
            if attrs.get(ATTR_LK_INTERRUPTED):
                self._set(span, ATTR_TURN_INTERRUPTED, True)
            # Prefer index stamped at on_start (open turn). Recompute via the
            # same rules as pipeline children — never trust a missing index.
            turn_index_raw = (span.attributes or {}).get(ATTR_TURN_INDEX)
            if turn_index_raw is None:
                resolved_turn_index = self.active_turn_index(state, "agent_turn") or (
                    state.open_agent_turn_index or (state.turn_count + 1)
                )
            else:
                resolved_turn_index = attr_int(span.attributes or {}, ATTR_TURN_INDEX)
            if resolved_turn_index:
                self._set(span, ATTR_TURN_INDEX, resolved_turn_index)
            agent_text = state.agent_text_by_turn.get(resolved_turn_index, "")
            if agent_text:
                self._set(span, ATTR_TURN_AGENT_TEXT, agent_text)
            self._stash_turn_pipeline_attrs(
                state,
                resolved_turn_index,
                self._pipeline_attrs_from_agent_turn(span, state),
            )
            return

        if state.open_agent_turn_index is None:
            transcript = str(
                attr_get(attrs, ATTR_LK_USER_TRANSCRIPT, ATTR_USER_TRANSCRIPT_LEGACY)
                or attr_get(attrs, ATTR_LK_USER_INPUT, ATTR_USER_INPUT_LEGACY)
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
        agent_modality = state.last_user_input_modality or self._user_turn_modality(attrs)
        response_text = str(
            attr_get(
                attrs, ATTR_LK_RESPONSE_TEXT, ATTR_RESPONSE_TEXT_LEGACY, default=""
            )
            or ""
        ).strip()
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
            utterance_text=response_text,
        )
        state.turn_count = turn_index
        state.open_agent_turn_index = None

        self._stamp_agent_turn_timing_attrs(span, attrs)

        if attrs.get(ATTR_LK_INTERRUPTED):
            self._set(span, ATTR_TURN_INTERRUPTED, True)

        if response_text:
            self._set(span, ATTR_TURN_AGENT_TEXT, response_text)

        if self._metrics and state.parlot_session_id:
            self._metrics.record_turn(
                state,
                e2e_latency_s=optional_float(attrs.get(ATTR_LK_E2E_LATENCY)),
                llm_ttft_s=optional_float(attrs.get(ATTR_LK_RESPONSE_TTFT)),
                tts_ttfb_s=state.pending_tts_ttfb_s,
                transcription_delay_s=optional_float(
                    attrs.get(ATTR_TRANSCRIPTION_DELAY)
                ),
                eou_delay_s=optional_float(attrs.get(ATTR_END_OF_TURN_DELAY)),
                interrupted=bool(attrs.get(ATTR_LK_INTERRUPTED)),
                participant_role="agent",
            )
            state.pending_tts_ttfb_s = None

        if self._genai_content_enabled(state):
            user_input = attr_get(
                attrs, ATTR_LK_USER_INPUT, ATTR_USER_INPUT_LEGACY, default=""
            )
            if user_input:
                self._add_event(
                    span,
                    EVENT_GEN_AI_USER_MESSAGE,
                    {"content": str(user_input)},
                )
            response = attr_get(
                attrs, ATTR_LK_RESPONSE_TEXT, ATTR_RESPONSE_TEXT_LEGACY, default=""
            )
            if response:
                self._add_event(
                    span,
                    EVENT_GEN_AI_ASSISTANT_MESSAGE,
                    {"content": str(response)},
                )

    def enrich_drain(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        """Lifecycle drain only — not a conversational turn boundary."""
        self._stamp_agent_identity(span, state)

    def enrich_eou(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "end_of_utterance_detection")
        lang = str(attrs.get(ATTR_EOU_LANGUAGE, "")).strip()
        if lang:
            state.languages_seen.add(lang)
            self._set(span, ATTR_VOICE_EOU_LANGUAGE, lang)
        self._stamp_events_user_text(span, state)

    def enrich_amd(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        self._set(span, ATTR_AGENT_ROLE, "amd")
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "classify_contact")

        category = str(attrs.get(ATTR_AMD_CATEGORY, "")).strip().lower()
        if category:
            self._set(span, ATTR_VOICE_AMD_CATEGORY, category)
        amd = AMD_CATEGORY_TO_CONTACT_TYPE.get(category, "unknown")
        self._set(span, ATTR_SESSION_AMD, amd)
        state.amd = amd

        self._stamp_agent_identity(span, state, attrs)

        if state.turn_count == 0 and state.open_agent_turn_index is None:
            self._set(span, ATTR_TURN_INDEX, 0)

    def merge_native_turn_attrs_onto_parlot_turns(
        self, spans: list[ReadableSpan]
    ) -> None:
        """Copy pipeline-only attrs from native turn spans onto ``parlot.turn``."""
        bootstrap = get_job_bootstrap()
        state = bootstrap.state if bootstrap is not None else None

        for span in spans:
            name = span.name or ""
            if name not in NATIVE_TURN_SPANS or state is None:
                continue
            attrs = span.attributes or {}
            # Require an explicit turn index — never guess from turn_count at export
            # time (mis-attributes long agent_turn bounds onto a late parlot.turn).
            turn_index = attr_int(attrs, ATTR_TURN_INDEX)
            if not turn_index:
                continue
            if name == "user_turn":
                self._stash_turn_pipeline_attrs(
                    state, turn_index, self._pipeline_attrs_from_user_turn(span, state)
                )
            else:
                self._stash_turn_pipeline_attrs(
                    state, turn_index, self._pipeline_attrs_from_agent_turn(span, state)
                )

        if state is None:
            return
        for span in spans:
            if span.name != SPAN_PARLOT_TURN:
                continue
            attrs = span.attributes or {}
            turn_index = attr_int(attrs, ATTR_TURN_INDEX)
            pending = state.pending_turn_pipeline_attrs.get(turn_index)
            if not pending:
                continue
            for key, value in pending.items():
                if attrs.get(key) in (None, "", 0, 0.0):
                    self._set(span, key, value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _modality_for_user_text(
        self,
        text: str,
        state: _LiveKitSessionState,
        metrics: Mapping[str, float] | None = None,
    ) -> str:
        if state.pending_interrupt_speech_end_wall_ms > 0:
            return "voice"
        if state.pending_user_speaker_id or state.pending_user_language:
            return "voice"
        # ChatMessage.metrics speaking timestamps imply a voice turn even when
        # user_input_transcribed did not stash a speaker id.
        if metrics and metrics.get("started_speaking_at") is not None:
            return "voice"
        return "text"

    def _stash_interrupt_boundary(
        self, state: _LiveKitSessionState, metrics: Mapping[str, float]
    ) -> None:
        wall = self._speech_wall_ms_from_metrics(metrics)
        if wall is None:
            return
        speech_start_wall_ms, speech_end_wall_ms = wall
        _, media_end_ms = self._recording.media_segments_from_speech(
            state, speech_start_wall_ms, speech_end_wall_ms
        )
        if media_end_ms <= 0:
            return
        state.pending_interrupt_media_end_ms = media_end_ms
        state.pending_interrupt_speech_end_wall_ms = speech_end_wall_ms

    @staticmethod
    def _speech_wall_ms_from_metrics(
        metrics: Mapping[str, float] | None,
    ) -> tuple[int, int] | None:
        if not metrics:
            return None
        started = metrics.get("started_speaking_at")
        stopped = metrics.get("stopped_speaking_at")
        if started is None or stopped is None:
            return None
        try:
            speech_start_wall_ms = int(float(started) * 1000)
            speech_end_wall_ms = int(float(stopped) * 1000)
        except (TypeError, ValueError):
            return None
        if speech_end_wall_ms <= speech_start_wall_ms:
            return None
        return speech_start_wall_ms, speech_end_wall_ms

    @staticmethod
    def _remember_agent_speech_end(
        state: _LiveKitSessionState, metrics: Mapping[str, float] | None
    ) -> None:
        wall = TurnEnricher._speech_wall_ms_from_metrics(metrics)
        if wall is None:
            return
        _, end_ms = wall
        if end_ms > state.last_agent_speech_end_wall_ms:
            state.last_agent_speech_end_wall_ms = end_ms

    @staticmethod
    def _clamp_user_speech_wall(
        state: _LiveKitSessionState, start_ms: int, end_ms: int
    ) -> tuple[int, int]:
        """Clamp user speech start to after the prior agent finished speaking.

        LiveKit's ChatMessage.metrics.started_speaking_at is the first
        voice-activity-detection (VAD) start of speech of the open user_turn —
        when the detector first thinks the caller began talking, not necessarily
        the burst that produced the final transcript. That start-of-speech can
        fire before/during an agent greeting, so the reported window spans the
        greeting and inverts timeline order.
        """
        floor = state.last_agent_speech_end_wall_ms
        if floor <= 0 or start_ms >= floor:
            return start_ms, end_ms
        start_ms = floor
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        return start_ms, end_ms

    def _resolve_user_participant_from_state(
        self, state: _LiveKitSessionState
    ) -> tuple[str, str]:
        if state.pending_user_speaker_id:
            participant_id = state.pending_user_speaker_id
            diarization_source = ATTR_DIAR_SOURCE_STT_EVENT
        else:
            participant_id = ATTR_TURN_PARTICIPANT_ID_CALLER
            diarization_source = self._user_turn_diarization_source(
                "voice" if state.pending_user_language else "text"
            )
        return participant_id, diarization_source

    @staticmethod
    def _user_turn_role(state: _LiveKitSessionState, participant_id: str) -> str:
        if participant_id in state.human_rep_participant_ids:
            return "human_rep"
        return "user"

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
        identity = str(
            attr_get(
                attrs,
                ATTR_PARTICIPANT_IDENTITY,
                ATTR_PARTICIPANT_IDENTITY_LEGACY,
                default="",
            )
            or ""
        ).strip()
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
        user_role = self._user_turn_role(state, participant_id)
        self._emit_turn_trace(
            state,
            turn_index=state.turn_count,
            role=user_role,
            participant_id=participant_id,
            diarization_source=diarization_source,
            input_modality=modality,
            agent_hint=agent_hint,
            source_span=span if modality == "voice" else None,
            language=state.pending_user_language,
            utterance_text=transcript,
        )
        state.open_agent_turn_index = state.turn_count + 1

        if self._genai_content_enabled(state):
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
            active = self.active_turn_index(state, span.name)
            if active is None:
                return
            resolved_turn_index = active
            self._set(span, ATTR_TURN_INDEX, active)
        else:
            resolved_turn_index = attr_int(attrs, ATTR_TURN_INDEX)
        text = state.user_text_by_turn.get(resolved_turn_index, "")
        if not text:
            return
        self._set(span, ATTR_TURN_USER_TEXT, text)
        if self._genai_content_enabled(state):
            self._add_event(
                span,
                EVENT_GEN_AI_USER_MESSAGE,
                {"content": text},
            )

    def _stash_turn_pipeline_attrs(
        self,
        state: _LiveKitSessionState,
        turn_index: int,
        attrs: dict[str, AttributeValue],
    ) -> None:
        if turn_index <= 0 or not attrs:
            return
        bucket = state.pending_turn_pipeline_attrs.setdefault(turn_index, {})
        for key, value in attrs.items():
            if value is None:
                continue
            if key not in bucket or bucket[key] in ("", 0, 0.0):
                bucket[key] = value

    @staticmethod
    def _speech_media_from_span_allowed(
        role: str, input_modality: str
    ) -> bool:
        """Native span bounds are speech windows for voice **user** turns only.

        Agent ``agent_turn`` spans cover AgentTasks/tools and must not drive
        ``speech_wall_*`` / ``media_segment_*``. Text/console turns never get
        recording-relative media from OTLP bounds.
        """
        return input_modality == "voice" and role != "agent"

    @staticmethod
    def _speech_media_from_metrics_allowed(input_modality: str) -> bool:
        return input_modality == "voice"

    def _pipeline_attrs_from_user_turn(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> dict[str, AttributeValue]:
        out: dict[str, AttributeValue] = {}
        attrs = span.attributes or {}
        confidence = optional_float(attrs.get(ATTR_VOICE_STT_CONFIDENCE))
        if confidence is None:
            confidence = optional_float(attrs.get(ATTR_TRANSCRIPT_CONFIDENCE))
        if confidence is not None:
            out[ATTR_VOICE_STT_CONFIDENCE] = confidence
        if self._user_turn_modality(attrs) != "voice":
            return out
        wall = self._recording.speech_wall_ms_from_span(span)
        if wall is not None:
            start_ms, end_ms = self._clamp_user_speech_wall(state, *wall)
            out[ATTR_TURN_SPEECH_WALL_START_MS] = start_ms
            out[ATTR_TURN_SPEECH_WALL_END_MS] = end_ms
            media_start, media_end = self._recording.media_segments_from_speech(
                state, start_ms, end_ms
            )
            if media_end > 0:
                out[ATTR_TURN_MEDIA_START_MS] = media_start
                out[ATTR_TURN_MEDIA_END_MS] = media_end
        return out

    def _pipeline_attrs_from_agent_turn(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> dict[str, AttributeValue]:
        """Latency/interrupt attrs from native agent_turn — never speech/media.

        Full agent_turn span bounds include AgentTasks/tools and must not become
        ``speech_wall_*`` / ``media_segment_*``. Those come from ChatMessage
        metrics at emit time only.
        """
        out: dict[str, AttributeValue] = {}
        attrs = span.attributes or {}
        for src, dest in (
            (ATTR_TURN_E2E_LATENCY_S, ATTR_TURN_E2E_LATENCY_S),
            (ATTR_TURN_LLM_TTFT_S, ATTR_TURN_LLM_TTFT_S),
            (ATTR_TURN_TRANSCRIPTION_DELAY_S, ATTR_TURN_TRANSCRIPTION_DELAY_S),
            (ATTR_TURN_EOU_DELAY_S, ATTR_TURN_EOU_DELAY_S),
            (ATTR_TURN_TTS_TTFB_S, ATTR_TURN_TTS_TTFB_S),
        ):
            val = optional_float(attrs.get(src))
            if val is None and src == ATTR_TURN_E2E_LATENCY_S:
                val = optional_float(attrs.get(ATTR_LK_E2E_LATENCY))
            if val is None and src == ATTR_TURN_LLM_TTFT_S:
                val = optional_float(attrs.get(ATTR_LK_RESPONSE_TTFT))
            if val is None and src == ATTR_TURN_TRANSCRIPTION_DELAY_S:
                val = optional_float(attrs.get(ATTR_TRANSCRIPTION_DELAY))
            if val is None and src == ATTR_TURN_EOU_DELAY_S:
                val = optional_float(attrs.get(ATTR_END_OF_TURN_DELAY))
            if val is not None:
                out[dest] = val
        if state.pending_tts_ttfb_s is not None:
            out[ATTR_TURN_TTS_TTFB_S] = state.pending_tts_ttfb_s
        if attrs.get(ATTR_LK_INTERRUPTED) or attrs.get(ATTR_TURN_INTERRUPTED):
            out[ATTR_TURN_INTERRUPTED] = True
        return out

    def _stamp_agent_turn_timing_attrs(
        self, span: ReadableSpan, attrs: Mapping[str, AttributeValue]
    ) -> None:
        e2e = optional_float(attrs.get(ATTR_LK_E2E_LATENCY))
        if e2e is not None:
            self._set(span, ATTR_TURN_E2E_LATENCY_S, e2e)
        ttft = optional_float(attrs.get(ATTR_LK_RESPONSE_TTFT))
        if ttft is not None:
            self._set(span, ATTR_TURN_LLM_TTFT_S, ttft)
        transcription_delay = optional_float(attrs.get(ATTR_TRANSCRIPTION_DELAY))
        if transcription_delay is not None:
            self._set(span, ATTR_TURN_TRANSCRIPTION_DELAY_S, transcription_delay)
        eou_delay = optional_float(attrs.get(ATTR_END_OF_TURN_DELAY))
        if eou_delay is not None:
            self._set(span, ATTR_TURN_EOU_DELAY_S, eou_delay)

    @staticmethod
    def _user_turn_modality(attrs: Mapping[str, AttributeValue]) -> str:
        """``voice`` when STT produced a transcript; ``text`` for typed/console input."""
        if str(
            attr_get(
                attrs,
                ATTR_LK_USER_TRANSCRIPT,
                ATTR_USER_TRANSCRIPT_LEGACY,
                default="",
            )
            or ""
        ).strip():
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
            TurnEnricher._user_turn_diarization_source(modality),
        )

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
        """Events mode: export user utterance on session_agents at the user turn index.

        Voice only — text sessions stamp ``turn.user_text`` on ``parlot.turn`` and
        do not mint synthetic stt companions.
        """
        if modality == "text":
            return
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
            ATTR_AGENT_ROLE: "stt",
            ATTR_AGENT_STAGE: "turn",
        }
        if participant_id and participant_id != ATTR_TURN_PARTICIPANT_ID_CALLER:
            attrs[ATTR_PARTICIPANT_CHANNEL_IDENTITY] = participant_id
        if state.session_id:
            attrs[ATTR_LK_JOB_ID] = state.session_id
        if state.room_name:
            attrs[ATTR_LK_ROOM_NAME] = state.room_name
        if state.room_sid:
            attrs[ATTR_LK_ROOM_SID] = state.room_sid

        span = self._tracer.start_span(SPAN_VOICE_STT, attributes=attrs)
        stamp_livekit_platform_refs(
            span,
            job_id=state.session_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )
        if self._genai_content_enabled(state):
            span.add_event(EVENT_GEN_AI_USER_MESSAGE, {"content": text})
        span.end()

    def _emit_committed_agent_utterance_span(
        self,
        state: _LiveKitSessionState,
        *,
        turn_index: int,
        text: str,
        modality: str,
        participant_id: str,
    ) -> None:
        """Events mode: export agent utterance for timeline join at the agent turn index.

        Voice only — text sessions stamp ``turn.agent_text`` on ``parlot.turn``.
        Real ``tts``/``chat`` node/run spans still own pipeline timing.
        """
        if modality == "text":
            return
        if self._turn_source != "events" or not self._tracer or not state.parlot_session_id:
            return
        attrs: dict[str, AttributeValue] = {
            ATTR_SESSION_ID: state.parlot_session_id,
            ATTR_SESSION_CONVERSATION_ID: state.conversation_id,
            ATTR_GEN_AI_CONVERSATION_ID: state.conversation_id,
            ATTR_TURN_INDEX: turn_index,
            ATTR_TURN_AGENT_TEXT: text,
            ATTR_TURN_INPUT_MODALITY: modality,
            ATTR_AGENT_FRAMEWORK: "livekit",
            ATTR_TURN_PARTICIPANT_ID: participant_id,
            ATTR_PARTICIPANT_DIAR_SOURCE: ATTR_DIAR_SOURCE_AGENT_ID,
            ATTR_AGENT_ROLE: "tts",
            ATTR_AGENT_STAGE: "turn",
        }
        if state.session_id:
            attrs[ATTR_LK_JOB_ID] = state.session_id
        if state.room_name:
            attrs[ATTR_LK_ROOM_NAME] = state.room_name
        if state.room_sid:
            attrs[ATTR_LK_ROOM_SID] = state.room_sid

        span = self._tracer.start_span(SPAN_VOICE_TTS, attributes=attrs)
        stamp_livekit_platform_refs(
            span,
            job_id=state.session_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )
        if self._genai_content_enabled(state):
            span.add_event(EVENT_GEN_AI_ASSISTANT_MESSAGE, {"content": text})
        span.end()

    def _resolve_turn_language(
        self,
        state: _LiveKitSessionState,
        *,
        role: str,
        turn_index: int,
        language: str,
        utterance_text: str = "",
    ) -> tuple[str, str]:
        resolved = language.strip()
        if not resolved:
            text = utterance_text.strip()
            if not text:
                if role == "agent":
                    text = state.agent_text_by_turn.get(turn_index, "")
                else:
                    text = state.user_text_by_turn.get(turn_index, "")
            detected = detect_language_from_text(text) if text else None
            if detected:
                resolved = detected
            elif role == "agent":
                resolved = state.last_user_turn_language or state.pending_user_language

        language_switch = ""
        if resolved:
            state.languages_seen.add(resolved)
            prev = (
                state.last_user_turn_language
                if role == "user"
                else state.last_agent_turn_language
            )
            if prev and prev != resolved:
                language_switch = json.dumps({"from": prev, "to": resolved})
            if role == "user":
                state.last_user_turn_language = resolved
            else:
                state.last_agent_turn_language = resolved

        return resolved, language_switch

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
        speech_wall_override: tuple[int, int] | None = None,
        media_segment_override: tuple[int, int] | None = None,
        language: str = "",
        utterance_text: str = "",
    ) -> None:
        if not self._tracer or not state.parlot_session_id:
            return
        resolved_language, language_switch = self._resolve_turn_language(
            state,
            role=role,
            turn_index=turn_index,
            language=language,
            utterance_text=utterance_text,
        )
        active_agent_id = (
            topology_agent_name(agent_hint)
            or topology_agent_name(state.agent_label)
            or "unknown"
        )
        prev = state.last_turn_trace_id

        speech_wall: tuple[int, int] | None = speech_wall_override
        start_time_unix_ns: int | None = None
        end_time_unix_ns: int | None = None
        if (
            speech_wall is None
            and source_span is not None
            and self._speech_media_from_span_allowed(role, input_modality)
        ):
            speech_wall = self._recording.speech_wall_ms_from_span(source_span)
            if speech_wall is not None:
                start_time_unix_ns = source_span.start_time
                end_time_unix_ns = source_span.end_time

        media_start_ms = 0
        media_end_ms = 0
        speech_start_wall_ms: int | None = None
        speech_end_wall_ms: int | None = None
        if media_segment_override is not None:
            media_start_ms, media_end_ms = media_segment_override
        if speech_wall is not None:
            speech_start_wall_ms, speech_end_wall_ms = speech_wall
            if media_segment_override is None:
                media_start_ms, media_end_ms = self._recording.media_segments_from_speech(
                    state, speech_start_wall_ms, speech_end_wall_ms
                )
            if start_time_unix_ns is None:
                start_time_unix_ns = speech_start_wall_ms * 1_000_000
                end_time_unix_ns = speech_end_wall_ms * 1_000_000

        metrics = turn_metrics or {}
        if speech_wall is None and self._speech_media_from_metrics_allowed(
            input_modality
        ):
            wall_from_metrics = self._speech_wall_ms_from_metrics(metrics)
            if wall_from_metrics is not None:
                speech_start_wall_ms, speech_end_wall_ms = wall_from_metrics
                speech_wall = (speech_start_wall_ms, speech_end_wall_ms)
                start_time_unix_ns = speech_start_wall_ms * 1_000_000
                end_time_unix_ns = speech_end_wall_ms * 1_000_000
                media_start_ms, media_end_ms = self._recording.media_segments_from_speech(
                    state, speech_start_wall_ms, speech_end_wall_ms
                )

        # LiveKit first start-of-speech user windows can precede the prior agent greeting.
        if (
            role == "user"
            and speech_wall is not None
            and speech_start_wall_ms is not None
            and speech_end_wall_ms is not None
        ):
            clamped_start, clamped_end = self._clamp_user_speech_wall(
                state, speech_start_wall_ms, speech_end_wall_ms
            )
            if (clamped_start, clamped_end) != (speech_start_wall_ms, speech_end_wall_ms):
                speech_start_wall_ms, speech_end_wall_ms = clamped_start, clamped_end
                speech_wall = (speech_start_wall_ms, speech_end_wall_ms)
                start_time_unix_ns = speech_start_wall_ms * 1_000_000
                end_time_unix_ns = speech_end_wall_ms * 1_000_000
                if media_segment_override is None:
                    media_start_ms, media_end_ms = (
                        self._recording.media_segments_from_speech(
                            state, speech_start_wall_ms, speech_end_wall_ms
                        )
                    )

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
            language=resolved_language,
            language_switch=language_switch,
            utterance_text=utterance_text,
        )
        state.last_turn_trace_id = trace_id
        state.turn_trace_by_index[turn_index] = trace_id
        state.turn_root_span_by_index[turn_index] = root_span_id
        self._turn_trace_registry.setdefault(state.parlot_session_id, {})[
            turn_index
        ] = (trace_id, root_span_id)

        if role == "agent" and active_agent_id != "unknown":
            state.topology.push_agent_chain(active_agent_id)
            if state.topology.active_segment is None and not state.topology.intent_segments:
                state.topology.open_bootstrap_segment(active_agent_id, turn_index)
            state.topology.apply_pending_from_turn_on_emit(turn_index)
