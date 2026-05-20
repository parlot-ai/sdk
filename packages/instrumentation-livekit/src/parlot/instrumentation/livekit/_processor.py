"""
LiveKitGenAIProcessor — enriches LiveKit Agents OTel spans in-place.

Verified span names and attributes (livekit-agents 1.5.x):
─────────────────────────────────────────────────────────
Span name             Key attributes
────────────────────  ──────────────────────────────────────────────────
job_entrypoint        lk.agent_name, lk.job_id, lk.room_name
llm_request_run       gen_ai.request.model, gen_ai.provider.name,
                      gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
                      gen_ai.usage.input_cached_tokens,
                      gen_ai.usage.input_audio_tokens, etc.
llm_node              lk.response.text, gen_ai.request.model,
                      gen_ai.provider.name
tts_node              gen_ai.request.model, gen_ai.provider.name,
                      lk.response.ttfb
tts_request_run       gen_ai.request.model(?), lk.input_text,
                      lk.response.ttfb, lk.retry_count
function_tool         lk.function_tool.id, lk.function_tool.name,
                      lk.function_tool.arguments,
                      lk.function_tool.output, lk.function_tool.is_error
drain_agent_activity  lk.agent_label, lk.generation_id,
                      lk.parent_generation_id, lk.user_input,
                      lk.instructions, lk.interrupted,
                      lk.speech_id, lk.response.text, lk.e2e_latency
eou_detection         lk.is_interruption, eou probability attrs
judge_evaluation      gen_ai.operation.name="judge" (test-only)

NOTE on handoffs: there is NO dedicated handoff span in LK 1.5.x.
Handoffs surface as a function_tool span (auto-detected via output repr)
or as a conversation_item_added session event (handled by install_handoff_hook
in _hooks.py).  For explicit control, pass handoff_tool_names to the
constructor; for BYO TracerProvider, construct this class directly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import FrozenSet, Optional

from opentelemetry.sdk.trace import ReadableSpan

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_GEN_AI_AUDIO_IN,
    ATTR_GEN_AI_AUDIO_OUT,
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
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
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_AGENT_NAME,
    ATTR_LK_E2E_LATENCY,
    ATTR_LK_FNC_TOOL_ARGS,
    ATTR_LK_FNC_TOOL_ERROR,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FNC_TOOL_OUTPUT,
    ATTR_LK_HANDOFF_CREATED_AT,
    ATTR_LK_HANDOFF_INDEX,
    ATTR_LK_HANDOFF_TARGET,
    ATTR_LK_HANDOFF_TRANSITION,
    ATTR_LK_INTERRUPTED,
    ATTR_LK_IS_INTERRUPTION,
    ATTR_LK_JOB_ID,
    ATTR_LK_RESPONSE_TEXT,
    ATTR_LK_RESPONSE_TTFB,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
    ATTR_LK_SESSION_AGENT_CHAIN,
    ATTR_LK_SESSION_COST_USD,
    ATTR_LK_SESSION_HANDOFFS,
    ATTR_LK_SESSION_INPUT_TOKENS,
    ATTR_LK_SESSION_OUT_TOKENS,
    ATTR_LK_SESSION_TOOL_CALLS,
    ATTR_LK_SESSION_TURNS,
    ATTR_LK_TOOL_CALL_INDEX,
    ATTR_LK_TURN_E2E_LATENCY,
    ATTR_LK_TURN_INDEX,
    ATTR_LK_TURN_INTERRUPTED,
    ATTR_LK_TTS_INPUT_TEXT,
    ATTR_LK_USER_INPUT,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_INDEX,
)
from parlot.core.ids import new_session_id
from ._platform_refs import (
    clear_livekit_job_context,
    lookup_room_context,
    stamp_livekit_platform_refs,
)
from parlot.core.pricing import DEFAULT_PRICES, compute_cost
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.session import SessionState as _BaseSessionState
from ._turn_traces import emit_turn_root_span

logger = logging.getLogger("parlot.instrumentation.livekit")

_AGENT_PIPELINE_SPANS: FrozenSet[str] = frozenset({
    "llm_node",
    "llm_request_run",
    "tts_node",
    "tts_request_run",
    "function_tool",
    "drain_agent_activity",
})


# ---------------------------------------------------------------------------
# LiveKit-specific session accumulator
# ---------------------------------------------------------------------------

@dataclass
class _LiveKitSessionState(_BaseSessionState):
    agent_chain: list[str] = field(default_factory=list)
    # Set when a handoff span ends; cleared when the next LLM span starts.
    # Used to compute the dead-air transition latency between agents.
    pending_handoff_end_ns: int = 0
    parlot_session_id: str = ""
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    turn_trace_by_index: dict[int, str] = field(default_factory=dict)
    turn_root_span_by_index: dict[int, str] = field(default_factory=dict)
    open_agent_turn_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class LiveKitGenAIProcessor(ParlotBaseProcessor):
    """
    Enriches LiveKit Agent spans in-place with:
    - gen_ai.system (inferred from provider name when missing)
    - gen_ai.usage.cost_usd (computed from token counts)
    - gen_ai.tool.is_handoff (True when a function_tool returns AgentHandoff)
    - lk.session.* aggregate fields on the job_entrypoint root span
    - platform.ref.* correlation IDs stamped on every span

    Does NOT wrap a downstream processor — add alongside BatchSpanProcessor:

        provider.add_span_processor(LiveKitGenAIProcessor())
        provider.add_span_processor(BatchSpanProcessor(your_exporter))

    Args:
        prices: Override or extend DEFAULT_PRICES with your own model prices.
            Keys are model name prefixes; values are (input_$/M, output_$/M).
        capture_content: When True, prompt and response text is captured as
            span events. Set False in PII-sensitive environments.
        handoff_tool_names: Explicit set of function tool names that trigger
            agent handoffs. Auto-detection via the output repr covers the
            standard LiveKit case; supply this only when you have non-standard
            handoff wrappers that don't produce "AgentHandoff" in their output.
    """

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
        # parlot session_id -> turn_index -> (trace_id, root_span_id)
        self._turn_trace_registry: dict[str, dict[int, tuple[str, str]]] = {}
        self._tracer = None  # set by configure() for per-turn root spans
        self._metrics = None  # ParlotMetricsRecorder from configure()

    def on_end(self, span: ReadableSpan) -> None:
        try:
            self._enrich(span)
        except Exception:
            logger.exception("LiveKitGenAIProcessor failed on span %r", span.name)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def set_tracer(self, tracer) -> None:
        """Called from configure() so turn roots can be exported."""
        self._tracer = tracer

    def set_metrics(self, metrics) -> None:
        """Called from configure() for OTLP metric export."""
        self._metrics = metrics

    def lookup_turn_trace(
        self, session_id: str, turn_index: int
    ) -> tuple[str, str] | None:
        """Return (trace_id, parlot.turn span_id) for export-time trace remapping."""
        by_turn = self._turn_trace_registry.get(session_id)
        if not by_turn:
            return None
        return by_turn.get(turn_index)

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
        name     = span.name
        attrs = span.attributes or {}
        job_key = str(attrs.get(ATTR_LK_JOB_ID) or self._trace_id_hex(span))
        state    = self._sessions.setdefault(job_key, _LiveKitSessionState())

        self._maybe_update(state, "session_id",  attrs.get(ATTR_LK_JOB_ID))
        self._maybe_update(state, "room_name",   attrs.get(ATTR_LK_ROOM_NAME))
        self._maybe_update(state, "room_sid",    attrs.get(ATTR_LK_ROOM_SID))
        self._maybe_update(state, "agent_label", attrs.get(ATTR_LK_AGENT_LABEL)
                                                 or attrs.get(ATTR_LK_AGENT_NAME))

        # Backfill room metadata from the job context registry if not yet set
        if state.session_id and not state.room_sid:
            rn, rs = lookup_room_context(state.session_id)
            self._maybe_update(state, "room_name", rn or None)
            self._maybe_update(state, "room_sid",  rs or None)

        # Stamp correlation IDs on every span for GROUP BY in the backend
        if state.session_id: self._set(span, ATTR_LK_JOB_ID,   state.session_id)
        if state.room_name:  self._set(span, ATTR_LK_ROOM_NAME, state.room_name)
        if state.room_sid:   self._set(span, ATTR_LK_ROOM_SID,  state.room_sid)

        stamp_livekit_platform_refs(
            span,
            job_id=state.session_id,
            room_name=state.room_name,
            room_sid=state.room_sid,
        )

        self._ensure_parlot_session(state)
        self._stamp_session_turn_attrs(span, state)
        self._set(span, ATTR_AGENT_FRAMEWORK, "livekit")

        if   name == "llm_request_run":      self._enrich_llm_request(span, state)
        elif name == "llm_node":             self._enrich_llm_node(span, state)
        elif name == "tts_node":             self._enrich_tts_node(span, state)
        elif name == "tts_request_run":      self._enrich_tts_request(span, state)
        elif name == "function_tool":        self._enrich_function_tool(span, state)
        elif name == "drain_agent_activity": self._enrich_turn(span, state)
        elif name == "eou_detection":        self._enrich_eou(span, state)
        elif name == "job_entrypoint":       self._enrich_root(span, state, job_key)

    # ------------------------------------------------------------------
    # llm_request_run — actual LLM API call
    # Adds: gen_ai.system, cost, cache hit rate, handoff transition latency
    # ------------------------------------------------------------------

    def _enrich_llm_request(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = _provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        model         = str(attrs.get(ATTR_GEN_AI_MODEL, ""))
        input_tokens  = int(attrs.get(ATTR_GEN_AI_IN_TOKENS,  0))
        output_tokens = int(attrs.get(ATTR_GEN_AI_OUT_TOKENS, 0))
        cached_tokens = int(attrs.get(ATTR_GEN_AI_CACHED_TOKENS, 0))

        cost = compute_cost(model, input_tokens, output_tokens, self._prices)
        if cost is not None:
            self._set(span, ATTR_GEN_AI_COST_USD, round(cost, 8))
            state.total_cost_usd += cost

        state.total_input_tokens  += input_tokens
        state.total_output_tokens += output_tokens

        if input_tokens and cached_tokens:
            self._set(span, ATTR_GEN_AI_CACHE_HIT_RATE,
                      round(cached_tokens / input_tokens, 4))

        if state.pending_handoff_end_ns and span.start_time:
            gap_ms = (span.start_time - state.pending_handoff_end_ns) / 1_000_000
            if 0 < gap_ms < 30_000:
                self._set(span, ATTR_LK_HANDOFF_TRANSITION, round(gap_ms, 2))
            state.pending_handoff_end_ns = 0

    # ------------------------------------------------------------------
    # llm_node — orchestration wrapper around llm_request_run
    # Adds: turn index, gen_ai.system, operation name
    # ------------------------------------------------------------------

    def _enrich_llm_node(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        if not attrs.get(ATTR_GEN_AI_SYSTEM):
            system = _provider_to_system(str(attrs.get(ATTR_GEN_AI_PROVIDER, "")))
            if system:
                self._set(span, ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "chat")

    # ------------------------------------------------------------------
    # tts_node — orchestration wrapper around tts_request_run
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # tts_request_run — actual TTS API call
    # ------------------------------------------------------------------

    def _enrich_tts_request(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "text_to_speech")

        if self._capture_content:
            text = attrs.get(ATTR_LK_TTS_INPUT_TEXT, "")
            if text:
                self._add_event(span, EVENT_GEN_AI_ASSISTANT_MESSAGE,
                                {"content": str(text), "modality": "text_for_speech"})

    # ------------------------------------------------------------------
    # function_tool — tool call span
    # ------------------------------------------------------------------

    def _enrich_function_tool(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        state.tool_call_count += 1
        self._set(span, ATTR_LK_TOOL_CALL_INDEX, state.tool_call_count)

        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "execute_tool")

        tool_name   = str(attrs.get(ATTR_LK_FNC_TOOL_NAME, ""))
        tool_output = str(attrs.get(ATTR_LK_FNC_TOOL_OUTPUT, ""))
        is_error    = bool(attrs.get(ATTR_LK_FNC_TOOL_ERROR, False))

        if span.end_time is not None and span.start_time is not None:
            self._set(span, ATTR_GEN_AI_TOOL_DURATION_MS,
                      round((span.end_time - span.start_time) / 1_000_000, 2))

        # Handoff detection:
        #   1. Explicit name list provided at construction
        #   2. Output contains "AgentHandoff" class name (LK uses repr())
        is_handoff = tool_name in self._handoff_tools or "AgentHandoff" in tool_output

        if is_handoff:
            state.handoff_count += 1
            self._set(span, ATTR_GEN_AI_TOOL_IS_HANDOFF, True)
            self._set(span, ATTR_LK_HANDOFF_INDEX, state.handoff_count)

            new_agent = _extract_new_agent(tool_output)
            if new_agent:
                self._set(span, ATTR_LK_HANDOFF_TARGET, new_agent)
                if not state.agent_chain or state.agent_chain[-1] != new_agent:
                    state.agent_chain.append(new_agent)

            state.pending_handoff_end_ns = span.end_time or time.time_ns()

        if self._capture_content:
            tool_args = attrs.get(ATTR_LK_FNC_TOOL_ARGS, "")
            if tool_args:
                self._add_event(span, EVENT_GEN_AI_TOOL_MESSAGE,
                                {"role": "tool", "content": str(tool_args),
                                 "direction": "input", "name": tool_name})
            if tool_output and not is_error:
                self._add_event(span, EVENT_GEN_AI_TOOL_MESSAGE,
                                {"role": "tool", "content": tool_output,
                                 "direction": "output", "name": tool_name})

    # ------------------------------------------------------------------
    # drain_agent_activity — one span per agent turn
    # ------------------------------------------------------------------

    def _enrich_turn(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}

        agent_turn_idx = state.open_agent_turn_index
        if agent_turn_idx is None:
            agent_turn_idx = state.turn_count + 1
        self._set(span, ATTR_LK_TURN_INDEX, agent_turn_idx)
        self._set(span, ATTR_TURN_INDEX, agent_turn_idx)
        agent_id = state.agent_label or "agent"
        self._emit_turn_trace(
            state,
            turn_index=agent_turn_idx,
            role="agent",
            participant_id=agent_id,
            label=agent_id,
            diarization_source="agent_id",
        )
        state.turn_count = agent_turn_idx
        state.open_agent_turn_index = None

        e2e = attrs.get(ATTR_LK_E2E_LATENCY)
        if e2e is not None:
            self._set(span, ATTR_LK_TURN_E2E_LATENCY, float(e2e))

        if attrs.get(ATTR_LK_INTERRUPTED):
            self._set(span, ATTR_LK_TURN_INTERRUPTED, True)

        if self._metrics and state.parlot_session_id:
            e2e = attrs.get(ATTR_LK_E2E_LATENCY)
            self._metrics.record_turn(
                state,
                e2e_latency_s=float(e2e) if e2e is not None else None,
                interrupted=bool(attrs.get(ATTR_LK_INTERRUPTED)),
            )

        if self._capture_content:
            user_input = attrs.get(ATTR_LK_USER_INPUT, "")
            if user_input:
                self._add_event(span, EVENT_GEN_AI_USER_MESSAGE,
                                {"content": str(user_input)})
            response = attrs.get(ATTR_LK_RESPONSE_TEXT, "")
            if response:
                self._add_event(span, EVENT_GEN_AI_ASSISTANT_MESSAGE,
                                {"content": str(response)})

    # ------------------------------------------------------------------
    # eou_detection — end-of-utterance, low-level voice timing span
    # ------------------------------------------------------------------

    def _enrich_eou(self, span: ReadableSpan, state: _LiveKitSessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(ATTR_GEN_AI_OP_NAME):
            self._set(span, ATTR_GEN_AI_OP_NAME, "end_of_utterance_detection")

        if attrs.get(ATTR_LK_IS_INTERRUPTION):
            return

        state.turn_count += 1
        self._set(span, ATTR_LK_TURN_INDEX, state.turn_count)
        self._set(span, ATTR_TURN_INDEX, state.turn_count)
        self._emit_turn_trace(
            state,
            turn_index=state.turn_count,
            role="user",
            participant_id="caller",
            diarization_source="livekit_vad",
        )
        state.open_agent_turn_index = state.turn_count + 1

    # ------------------------------------------------------------------
    # job_entrypoint — root span; write session-level aggregates then clean up
    # ------------------------------------------------------------------

    def _ensure_parlot_session(self, state: _LiveKitSessionState) -> None:
        if not state.parlot_session_id:
            state.parlot_session_id = new_session_id()
            state.conversation_id = state.parlot_session_id

    def _stamp_session_turn_attrs(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
        if state.parlot_session_id:
            self._set(span, ATTR_SESSION_ID, state.parlot_session_id)
            self._set(span, ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        active = self._active_turn_index(state, span.name)
        if active is not None:
            self._set(span, ATTR_TURN_INDEX, active)
            self._set(span, ATTR_LK_TURN_INDEX, active)

    def _emit_turn_trace(
        self,
        state: _LiveKitSessionState,
        *,
        turn_index: int,
        role: str,
        participant_id: str,
        label: str = "",
        diarization_source: str = "",
    ) -> None:
        if not self._tracer or not state.parlot_session_id:
            return
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
        )
        state.last_turn_trace_id = trace_id
        state.turn_trace_by_index[turn_index] = trace_id
        state.turn_root_span_by_index[turn_index] = root_span_id
        self._turn_trace_registry.setdefault(state.parlot_session_id, {})[
            turn_index
        ] = (trace_id, root_span_id)

    def _enrich_root(
        self, span: ReadableSpan, state: _LiveKitSessionState, job_key: str
    ) -> None:
        self._set(span, ATTR_LK_SESSION_TURNS,        state.turn_count)
        self._set(span, ATTR_LK_SESSION_TOOL_CALLS,   state.tool_call_count)
        self._set(span, ATTR_LK_SESSION_HANDOFFS,     state.handoff_count)
        self._set(span, ATTR_LK_SESSION_INPUT_TOKENS, state.total_input_tokens)
        self._set(span, ATTR_LK_SESSION_OUT_TOKENS,   state.total_output_tokens)

        if state.total_cost_usd:
            self._set(span, ATTR_LK_SESSION_COST_USD,
                      round(state.total_cost_usd, 6))

        if state.agent_chain:
            self._set(span, ATTR_LK_SESSION_AGENT_CHAIN,
                      " → ".join(state.agent_chain))

        if self._metrics and state.parlot_session_id:
            self._metrics.record_session_close(state)

        clear_livekit_job_context(state.session_id)
        self._sessions.pop(job_key, None)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _provider_to_system(provider: str) -> str:
    """Map livekit gen_ai.provider.name → gen_ai.system semconv value."""
    mapping = {
        "openai":     "openai",
        "anthropic":  "anthropic",
        "google":     "gcp.vertex_ai",
        "gemini":     "gcp.vertex_ai",
        "deepgram":   "deepgram",
        "elevenlabs": "elevenlabs",
        "cartesia":   "cartesia",
        "assemblyai": "assemblyai",
        "azure":      "azure",
        "silero":     "silero",
    }
    p = provider.lower()
    for key, val in mapping.items():
        if key in p:
            return val
    return ""


def _extract_new_agent(tool_output: str) -> str:
    """
    Pull the new agent class name from AgentHandoff repr (best-effort).
    LK repr looks like: AgentHandoff(agent=<BillingAgent object at 0x...>)
    """
    import re
    m = re.search(r"AgentHandoff\(agent=<(\w+)", tool_output)
    return m.group(1) if m else ""
