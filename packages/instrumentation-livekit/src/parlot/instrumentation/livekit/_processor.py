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
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_TOOL_CALL_INDEX,
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_LATENCY_MS,
    ATTR_AGENT_TRANSFER_SEQUENCE,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_AUDIO_IN,
    ATTR_GEN_AI_AUDIO_OUT,
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_COST_USD,
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
    ATTR_SESSION_CONTACT_TYPE,
    ATTR_SESSION_INTENT_SEQUENCE,
    ATTR_SESSION_TOPOLOGY_AGENTS,
    ATTR_SESSION_TOPOLOGY_EDGES,
    ATTR_SESSION_TOPOLOGY_ORCHESTRATOR_INSTRUCTIONS,
    ATTR_SESSION_TOPOLOGY_TOOLS,
    ATTR_TOOL_INPUT_PAYLOAD,
    ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
    ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_HANDOFF_COUNT,
    ATTR_SESSION_ID,
    ATTR_SESSION_TOOL_CALL_COUNT,
    ATTR_SESSION_TOTAL_COST_USD,
    ATTR_SESSION_TOTAL_INPUT_TOKENS,
    ATTR_SESSION_TOTAL_OUTPUT_TOKENS,
    ATTR_SESSION_TURN_COUNT,
    ATTR_TURN_E2E_LATENCY_S,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_INTERRUPTED,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_AMD_CATEGORY,
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_AGENT_NAME,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_FUNCTION_TOOLS,
    ATTR_LK_E2E_LATENCY,
    ATTR_LK_PROVIDER_TOOLS,
    ATTR_LK_TOOL_SETS,
    ATTR_LK_FNC_TOOL_ARGS,
    ATTR_LK_FNC_TOOL_ERROR,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_INTERRUPTED,
    ATTR_LK_IS_INTERRUPTION,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_RESPONSE_TTFB,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
    ATTR_LK_TTS_INPUT_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_LK_USER_TRANSCRIPT,
    METADATA_JOB_ID,
    METADATA_ROOM_ID,
)
from ._platform_refs import lookup_room_context, stamp_livekit_platform_refs
from ._session import (
    SPAN_CONVERSATION_SESSION,
    bootstrap_job_entrypoint,
    get_job_bootstrap,
    handle_conversation_session_on_end,
    teardown_job_entrypoint,
)
from parlot.core.pricing import DEFAULT_PRICES, compute_cost
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.session import SessionState as _BaseSessionState
from parlot.core.topology import SessionTopology

from ._topology import parse_chat_ctx_agent_config_updates
from ._turn_traces import emit_turn_root_span

logger = logging.getLogger("parlot.instrumentation.livekit")

_MAX_TOOL_PAYLOAD_CHARS = 8192
_TOOL_PREVIEW_CHARS = 512

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
    "lk.agent_handoff",
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
    pending_handoff_end_ns: int = 0
    parlot_session_id: str = ""
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    turn_trace_by_index: dict[int, str] = field(default_factory=dict)
    turn_root_span_by_index: dict[int, str] = field(default_factory=dict)
    open_agent_turn_index: Optional[int] = None
    contact_type: str = ""
    topology: SessionTopology = field(
        default_factory=lambda: SessionTopology(default_framework="livekit")
    )


class LiveKitGenAIProcessor(ParlotBaseProcessor):
    """Enriches LiveKit Agent spans in-place with Parlot conventions."""

    def __init__(
        self,
        prices: Optional[dict[str, tuple[float, float]]] = None,
        capture_content: bool = True,
        handoff_tool_names: Optional[set[str]] = None,
    ) -> None:
        self._prices = {**DEFAULT_PRICES, **(prices or {})}
        self._capture_content = capture_content
        self._handoff_tools = handoff_tool_names or set()
        self._sessions: dict[str, _LiveKitSessionState] = {}
        self._turn_trace_registry: dict[str, dict[int, tuple[str, str]]] = {}
        self._tracer = None
        self._metrics = None

    def on_start(self, span, parent_context=None) -> None:
        if span.name == "job_entrypoint":
            bootstrap_job_entrypoint(self, span)

    def on_end(self, span: ReadableSpan) -> None:
        try:
            logger.debug("on_end: %s attrs: %s", span.name, span.attributes)
            name = span.name
            if name == SPAN_CONVERSATION_SESSION:
                handle_conversation_session_on_end()
                return  # lifecycle owned by teardown_job_entrypoint
            if name == "job_entrypoint":
                teardown_job_entrypoint(self, span)
                return
            self._enrich(span)
        except Exception:
            logger.exception("LiveKitGenAIProcessor failed on span %r", span.name)

    def set_tracer(self, tracer) -> None:
        self._tracer = tracer

    def set_metrics(self, metrics) -> None:
        self._metrics = metrics

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
        logger.error(
            "parlot: no session bootstrap for span %s (trace=%s)",
            span.name,
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
            state.topology.upsert_agent(label_str)

    def _active_agent_id(
        self, state: _LiveKitSessionState, attrs: Mapping[str, AttributeValue]
    ) -> str:
        label = attrs.get(ATTR_LK_AGENT_LABEL) or attrs.get(ATTR_LK_AGENT_NAME)
        if label:
            return str(label)
        if state.agent_label:
            return state.agent_label
        if state.agent_chain:
            return state.agent_chain[-1]
        return "unknown"

    def _topology_turn_index(self, state: _LiveKitSessionState) -> int:
        if state.open_agent_turn_index is not None:
            return state.open_agent_turn_index
        return state.turn_count or 0

    def _active_turn_index(
        self, state: _LiveKitSessionState, span_name: str
    ) -> Optional[int]:
        if span_name == "job_entrypoint":
            return None
        if (
            state.open_agent_turn_index is not None
            and span_name in _AGENT_PIPELINE_SPANS
        ):
            return state.open_agent_turn_index
        if state.turn_count:
            return state.turn_count
        return None

    def _enrich(self, span: ReadableSpan) -> None:
        name = span.name
        if name in ("parlot.turn", SPAN_CONVERSATION_SESSION):
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
        elif name == "lk.agent_handoff":
            self._enrich_handoff(span, state)

    def _enrich_llm_request(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = _provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        model = str(attrs.get(ATTR_GEN_AI_MODEL, ""))
        input_tokens = _attr_int(attrs, ATTR_GEN_AI_IN_TOKENS)
        output_tokens = _attr_int(attrs, ATTR_GEN_AI_OUT_TOKENS)
        cached_tokens = _attr_int(attrs, ATTR_GEN_AI_CACHED_TOKENS)

        cost = compute_cost(model, input_tokens, output_tokens, self._prices)
        if cost is not None:
            self._set(span, ATTR_GEN_AI_COST_USD, round(cost, 8))
            state.total_cost_usd += cost

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

        agent_id = self._active_agent_id(state, attrs)
        state.topology.upsert_agent(agent_id)
        for tool_name in _coerce_str_sequence(attrs.get(ATTR_LK_FUNCTION_TOOLS)):
            state.topology.upsert_tool(tool_name)
        provider = _first_str_sequence(attrs.get(ATTR_LK_PROVIDER_TOOLS))
        tool_set = _first_str_sequence(attrs.get(ATTR_LK_TOOL_SETS))
        chat_raw = str(attrs.get(ATTR_LK_CHAT_CTX, ""))
        for item in parse_chat_ctx_agent_config_updates(chat_raw):
            instructions = item.get("instructions")
            if isinstance(instructions, str) and instructions:
                state.topology.record_instructions(agent_id, instructions)
            for added in _coerce_str_sequence(item.get("tools_added")):
                state.topology.upsert_tool(added, provider=provider, tool_set=tool_set)

        if self._capture_content:
            user_text, assistant_text = _preview_from_chat_ctx(chat_raw)
            if user_text:
                self._add_event(
                    span,
                    EVENT_GEN_AI_USER_MESSAGE,
                    {"content": user_text},
                )
            if assistant_text:
                self._add_event(
                    span,
                    EVENT_GEN_AI_ASSISTANT_MESSAGE,
                    {"content": assistant_text},
                )

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
            self._set(span, ATTR_GEN_AI_TTS_TTFB_S, float(ttfb))

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
        label = label_override or resolved.get(ATTR_LK_AGENT_LABEL) or state.agent_label
        if label:
            self._set(span, ATTR_GEN_AI_AGENT_NAME, str(label))

    def _enrich_function_tool(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        self._stamp_agent_identity(span, state, attrs)

        state.tool_call_count += 1
        self._set(span, ATTR_AGENT_TOOL_CALL_INDEX, state.tool_call_count)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "execute_tool")

        tool_name = str(attrs.get(ATTR_LK_FNC_TOOL_NAME, ""))
        tool_output = str(attrs.get(ATTR_LK_FNC_TOOL_OUTPUT, ""))
        is_error = bool(attrs.get(ATTR_LK_FNC_TOOL_ERROR, False))
        from_agent = self._active_agent_id(state, attrs)
        duration_ms = 0.0
        if span.end_time is not None and span.start_time is not None:
            duration_ms = round((span.end_time - span.start_time) / 1_000_000, 2)

        if tool_name:
            state.topology.upsert_tool(tool_name)
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
        if self._capture_content and tool_output and not is_error:
            out_preview = str(tool_output)[:_TOOL_PREVIEW_CHARS]
            self._set(span, ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW, out_preview)

        if span.end_time is not None and span.start_time is not None:
            self._set(span, ATTR_GEN_AI_TOOL_DURATION_MS, duration_ms)

        is_handoff = tool_name in self._handoff_tools or "AgentHandoff" in tool_output
        new_agent = _extract_new_agent(tool_output) if is_handoff else ""

        if tool_name and not is_handoff:
            state.topology.append_edge(
                from_agent,
                tool_name,
                "tool",
                latency_ms=duration_ms,
                error=is_error,
                turn_index=self._topology_turn_index(state),
                arguments=tool_args,
            )

        if is_handoff:
            state.handoff_count += 1
            self._set(span, ATTR_GEN_AI_TOOL_IS_HANDOFF, True)
            self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)

            if new_agent:
                self._set(span, ATTR_AGENT_TRANSFER_TO, new_agent)
                state.topology.upsert_agent(new_agent)
                state.topology.append_edge(
                    from_agent,
                    new_agent,
                    "agent",
                    latency_ms=duration_ms,
                    error=is_error,
                    turn_index=self._topology_turn_index(state),
                )
                if not state.agent_chain or state.agent_chain[-1] != new_agent:
                    state.agent_chain.append(new_agent)
                state.topology.open_segment_after_handoff(
                    new_agent, state.handoff_count, state.turn_count
                )

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

    def _record_user_turn(
        self,
        span: ReadableSpan,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue],
        *,
        transcript: str,
        modality: str,
    ) -> None:
        state.turn_count += 1
        self._set(span, ATTR_TURN_INDEX, state.turn_count)
        self._set(span, ATTR_TURN_INPUT_MODALITY, modality)
        agent_hint = str(
            attrs.get(ATTR_LK_AGENT_LABEL) or attrs.get(ATTR_LK_AGENT_NAME) or ""
        )
        self._emit_turn_trace(
            state,
            turn_index=state.turn_count,
            role="user",
            participant_id="caller",
            diarization_source=self._user_turn_diarization_source(modality),
            input_modality=modality,
            agent_hint=agent_hint,
        )
        state.open_agent_turn_index = state.turn_count + 1

        if self._capture_content:
            self._add_event(
                span,
                EVENT_GEN_AI_USER_MESSAGE,
                {"content": transcript},
            )

    def _enrich_user_turn(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
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
        agent_id = str(state.agent_label or "agent")
        self._emit_turn_trace(
            state,
            turn_index=turn_index,
            role="agent",
            participant_id=agent_id,
            label=agent_id,
            diarization_source="agent_id",
            agent_hint=agent_id,
        )
        state.turn_count = turn_index
        state.open_agent_turn_index = None

        e2e = attrs.get(ATTR_LK_E2E_LATENCY)
        if e2e is not None:
            self._set(span, ATTR_TURN_E2E_LATENCY_S, float(e2e))

        if attrs.get(ATTR_LK_INTERRUPTED):
            self._set(span, ATTR_TURN_INTERRUPTED, True)

        if self._metrics and state.parlot_session_id:
            self._metrics.record_turn(
                state,
                e2e_latency_s=float(e2e) if e2e is not None else None,
                interrupted=bool(attrs.get(ATTR_LK_INTERRUPTED)),
            )

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

    def _enrich_drain(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        """Lifecycle drain only — not a conversational turn boundary."""
        self._stamp_agent_identity(span, state)

    def _enrich_eou(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "end_of_utterance_detection")

    def _enrich_amd(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        self._set(span, ATTR_AGENT_ROLE, "amd")
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "classify_contact")

        category = str(attrs.get(ATTR_AMD_CATEGORY, "")).strip().lower()
        contact_type = _AMD_CATEGORY_TO_CONTACT_TYPE.get(category, "unknown")
        self._set(span, ATTR_SESSION_CONTACT_TYPE, contact_type)
        state.contact_type = contact_type

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
            if not state.agent_chain or state.agent_chain[-1] != target_str:
                state.agent_chain.append(target_str)
        else:
            self._stamp_agent_identity(span, state, attrs)

        if source is not None or target is not None:
            state.handoff_count += 1
            self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)
            src = str(source) if source is not None else self._active_agent_id(state, attrs)
            tgt = str(target) if target is not None else ""
            if src:
                state.topology.upsert_agent(src)
            if tgt:
                state.topology.upsert_agent(tgt)
            if src and tgt:
                latency_ms = 0.0
                if span.end_time is not None and span.start_time is not None:
                    latency_ms = round(
                        (span.end_time - span.start_time) / 1_000_000, 2
                    )
                state.topology.append_edge(
                    src,
                    tgt,
                    "agent",
                    latency_ms=latency_ms,
                    turn_index=self._topology_turn_index(state),
                )
            if tgt:
                state.topology.open_segment_after_handoff(
                    tgt, state.handoff_count, state.turn_count
                )

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
        return "livekit_vad" if modality == "voice" else "livekit_text_input"

    def _intent_agent_for_turn(
        self, state: _LiveKitSessionState, agent_hint: str = ""
    ) -> str:
        if agent_hint:
            return agent_hint
        if state.agent_label:
            return state.agent_label
        if state.topology.first_agent_label:
            return state.topology.first_agent_label
        if state.agent_chain:
            return state.agent_chain[-1]
        return "unknown"

    def _prepare_intent_for_turn_emit(
        self, state: _LiveKitSessionState, turn_index: int, agent_hint: str = ""
    ) -> tuple[str, str, str]:
        agent_id = self._intent_agent_for_turn(state, agent_hint)
        topo = state.topology
        if topo.active_segment is None:
            topo.open_bootstrap_segment(agent_id, from_turn=turn_index)
        topo.apply_pending_from_turn_on_emit(turn_index)
        return topo.active_intent_snapshot()

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
    ) -> None:
        if not self._tracer or not state.parlot_session_id:
            return
        intent_label, intent_key, active_agent_id = self._prepare_intent_for_turn_emit(
            state, turn_index, agent_hint=agent_hint
        )
        prev = state.last_turn_trace_id
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
            intent_label=intent_label,
            intent_key=intent_key,
            active_agent_id=active_agent_id,
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
        if state.total_cost_usd:
            session_span.set_attribute(
                ATTR_SESSION_TOTAL_COST_USD, round(state.total_cost_usd, 6)
            )
        if state.agent_chain:
            chain = " → ".join(state.agent_chain)
            session_span.set_attribute(ATTR_SESSION_AGENT_CHAIN, chain)
        topo = state.topology
        topo.finalize_intent_sequence(state.turn_count)
        seq = topo.intent_sequence_json()
        if seq and seq != "[]":
            session_span.set_attribute(ATTR_SESSION_INTENT_SEQUENCE, seq)
        if topo.agents_seen:
            session_span.set_attribute(ATTR_SESSION_TOPOLOGY_AGENTS, topo.agents_json())
        if topo.tools_seen:
            session_span.set_attribute(ATTR_SESSION_TOPOLOGY_TOOLS, topo.tools_json())
        if topo.edges:
            session_span.set_attribute(ATTR_SESSION_TOPOLOGY_EDGES, topo.edges_json())
        orch_instructions = topo.orchestrator_instructions()
        if orch_instructions:
            session_span.set_attribute(
                ATTR_SESSION_TOPOLOGY_ORCHESTRATOR_INSTRUCTIONS,
                orch_instructions,
            )
        if state.contact_type:
            session_span.set_attribute(ATTR_SESSION_CONTACT_TYPE, state.contact_type)
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
    if isinstance(value, (tuple, list)):
        return [str(v) for v in value if v is not None and str(v)]
    return [str(value)]


def _first_str_sequence(value: AttributeValue | None) -> str:
    items = _coerce_str_sequence(value)
    return items[0] if items else ""


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
        elif kind == "function_call":
            name = item.get("name", "")
            args = item.get("arguments", "")
            last_user = f"{name}({args})" if name else last_user
        elif kind == "function_call_output":
            out = item.get("output", "")
            if out:
                last_out = str(out)
    return last_user, last_out
