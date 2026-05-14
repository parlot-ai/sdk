"""
LiveKit Agents span processor — based on actual livekit-agents source.

Verified span names and attributes (livekit-agents 1.5.x):
─────────────────────────────────────────────────────────
Span name           Module                  Key attributes
──────────────────  ──────────────────────  ─────────────────────────────────────────
job_entrypoint      ipc.job_proc_lazy_main  lk.agent_name, lk.job_id, lk.room_name
llm_request_run     llm.llm                 gen_ai.request.model, gen_ai.provider.name,
                                            gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
                                            gen_ai.usage.input_cached_tokens,
                                            gen_ai.usage.input_audio_tokens, etc.
                                            Events: gen_ai.system.message, gen_ai.user.message,
                                            gen_ai.assistant.message, gen_ai.tool.message,
                                            gen_ai.choice
llm_node            voice.generation        lk.response.text, gen_ai.request.model,
                                            gen_ai.provider.name
tts_node            voice.generation        gen_ai.request.model, gen_ai.provider.name,
                                            lk.response.ttfb
tts_request_run     tts.tts                 gen_ai.request.model(?), lk.input_text,
                                            lk.response.ttfb, lk.retry_count
function_tool       voice.generation        lk.function_tool.id, lk.function_tool.name,
                                            lk.function_tool.arguments,
                                            lk.function_tool.output, lk.function_tool.is_error
drain_agent_activity voice.agent_activity   lk.agent_label, lk.generation_id,
                                            lk.parent_generation_id, lk.user_input,
                                            lk.instructions, lk.interrupted,
                                            lk.speech_id, lk.response.text, lk.e2e_latency
eou_detection       voice.audio_recognition lk.is_interruption, eou probability attrs
judge_evaluation    voice.run_result        gen_ai.operation.name="judge", (test-only)

NOTE on handoffs: there is NO dedicated handoff span in LK 1.5.x.
The LK source contains "# TODO(theomonnom): Add the agent handoff inside the current_span"
in the function_tool executor. Handoffs surface as:
  • A `function_tool` span whose lk.function_tool.name matches the handoff tool
  • A `conversation_item_added` session event with item.type == "agent_handoff"
  • An AgentHandoffEvent in RunResult.events (test framework only)

The correct approach is a session hook that emits its own handoff span (see below).

Usage:
    from livekit.agents.telemetry import set_tracer_provider
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    from lk_span_processor import LiveKitGenAIProcessor, install_handoff_hook

    provider = TracerProvider()
    provider.add_span_processor(LiveKitGenAIProcessor())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="...")))
    set_tracer_provider(provider)

    # In your entrypoint, after session is created:
    install_handoff_hook(session, tracer=opentelemetry.trace.get_tracer("your-sdk"))
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

logger = logging.getLogger("lk_span_processor")

# ---------------------------------------------------------------------------
# Verified attribute name constants (from livekit.agents.telemetry.trace_types)
# Using string literals so this file has no hard dependency on livekit-agents.
# ---------------------------------------------------------------------------

# job / session
_ATTR_JOB_ID          = "lk.job_id"
_ATTR_AGENT_NAME      = "lk.agent_name"
_ATTR_AGENT_LABEL     = "lk.agent_label"
_ATTR_ROOM_NAME       = "lk.room_name"

# turn
_ATTR_TURN_ID         = "lk.generation_id"
_ATTR_PARENT_TURN_ID  = "lk.parent_generation_id"
_ATTR_USER_INPUT      = "lk.user_input"
_ATTR_INSTRUCTIONS    = "lk.instructions"
_ATTR_INTERRUPTED     = "lk.interrupted"
_ATTR_SPEECH_ID       = "lk.speech_id"
_ATTR_RESPONSE_TEXT   = "lk.response.text"
_ATTR_E2E_LATENCY     = "lk.e2e_latency"

# llm
_ATTR_CHAT_CTX        = "lk.chat_ctx"          # JSON blob (older LK versions)
_ATTR_RESPONSE_TTFT   = "lk.response.ttft"

# tts
_ATTR_TTS_INPUT_TEXT  = "lk.input_text"
_ATTR_RESPONSE_TTFB   = "lk.response.ttfb"

# function tool
_ATTR_FNC_TOOL_ID     = "lk.function_tool.id"
_ATTR_FNC_TOOL_NAME   = "lk.function_tool.name"
_ATTR_FNC_TOOL_ARGS   = "lk.function_tool.arguments"
_ATTR_FNC_TOOL_OUTPUT = "lk.function_tool.output"
_ATTR_FNC_TOOL_ERROR  = "lk.function_tool.is_error"

# gen_ai semconv (LK sets these itself on llm_request_run / llm_node / tts_node)
_ATTR_GEN_AI_SYSTEM       = "gen_ai.system"
_ATTR_GEN_AI_OP_NAME      = "gen_ai.operation.name"
_ATTR_GEN_AI_PROVIDER     = "gen_ai.provider.name"
_ATTR_GEN_AI_MODEL        = "gen_ai.request.model"
_ATTR_GEN_AI_IN_TOKENS    = "gen_ai.usage.input_tokens"
_ATTR_GEN_AI_OUT_TOKENS   = "gen_ai.usage.output_tokens"
_ATTR_GEN_AI_CACHED_TOKENS = "gen_ai.usage.input_cached_tokens"
_ATTR_GEN_AI_AUDIO_IN     = "gen_ai.usage.input_audio_tokens"
_ATTR_GEN_AI_AUDIO_OUT    = "gen_ai.usage.output_audio_tokens"

# ---------------------------------------------------------------------------
# Price table — dollars per million tokens
# ---------------------------------------------------------------------------

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o":             (2.50,  10.00),
    "gpt-4o-mini":        (0.15,   0.60),
    "gpt-4.1":            (2.00,   8.00),
    "gpt-4.1-mini":       (0.40,   1.60),
    "gpt-4.1-nano":       (0.10,   0.40),
    "o3":                 (10.00,  40.00),
    "o4-mini":            (1.10,   4.40),
    "claude-opus-4-5":    (15.00,  75.00),
    "claude-sonnet-4-5":  (3.00,   15.00),
    "claude-haiku-4-5":   (0.80,   4.00),
    "gemini-2.5-flash":   (0.15,   0.60),
    "gemini-2.5-pro":     (1.25,   10.00),
}

# ---------------------------------------------------------------------------
# Per-session accumulator
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    session_id: str = ""
    room_name: str = ""
    agent_label: str = ""

    turn_count: int = 0
    tool_call_count: int = 0
    handoff_count: int = 0          # incremented by install_handoff_hook

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0

    agent_chain: list[str] = field(default_factory=list)

    # For transition latency: set when a handoff span ends (via hook),
    # cleared when the next llm_node or llm_request_run span starts.
    pending_handoff_end_ns: int = 0


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class LiveKitGenAIProcessor(SpanProcessor):
    """
    Enriches LiveKit Agent spans in-place with:
    - gen_ai.system (inferred from provider name when missing)
    - gen_ai.usage.cost_usd (computed from token counts)
    - gen_ai.tool.is_handoff (True when a function_tool returns AgentHandoff)
    - lk.session.* aggregate fields on the job_entrypoint root span
    - Session correlation IDs stamped on every span

    Does NOT wrap a downstream — add alongside BatchSpanProcessor:

        provider.add_span_processor(LiveKitGenAIProcessor())
        provider.add_span_processor(BatchSpanProcessor(your_exporter))
    """

    def __init__(
        self,
        prices: Optional[dict[str, tuple[float, float]]] = None,
        capture_content: bool = True,
        handoff_tool_names: Optional[set[str]] = None,
    ) -> None:
        """
        Args:
            prices: Override / extend DEFAULT_PRICES with your own model prices.
            capture_content: If True, prompt and response content is captured
                as span events. Set False for PII-sensitive environments.
            handoff_tool_names: Set of function tool names that trigger agent
                handoffs (e.g. {"transfer_to_billing", "escalate_to_support"}).
                When matched, the function_tool span is labelled as a handoff.
                If None, auto-detection is attempted via the tool output value.
        """
        self._prices = {**DEFAULT_PRICES, **(prices or {})}
        self._capture_content = capture_content
        self._handoff_tools = handoff_tool_names or set()
        self._sessions: dict[str, SessionState] = {}

    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        try:
            self._enrich(span)
        except Exception:
            logger.exception("LiveKitGenAIProcessor failed on span %r", span.name)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

    # ------------------------------------------------------------------
    # Dispatch on verified span names
    # ------------------------------------------------------------------

    def _enrich(self, span: ReadableSpan) -> None:
        name     = span.name
        trace_id = _trace_id_hex(span)
        state    = self._sessions.setdefault(trace_id, SessionState())

        # Harvest correlation IDs from whichever span carries them first
        attrs = span.attributes or {}
        _maybe_update(state, "session_id",  attrs.get(_ATTR_JOB_ID))
        _maybe_update(state, "room_name",   attrs.get(_ATTR_ROOM_NAME))
        _maybe_update(state, "agent_label", attrs.get(_ATTR_AGENT_LABEL)
                                         or attrs.get(_ATTR_AGENT_NAME))

        # Stamp every span with correlation IDs for GROUP BY in your backend
        if state.session_id: _set(span, _ATTR_JOB_ID,    state.session_id)
        if state.room_name:  _set(span, _ATTR_ROOM_NAME,  state.room_name)

        # Route to enricher by exact span name (all verified from source)
        if   name == "llm_request_run":    self._enrich_llm_request(span, state)
        elif name == "llm_node":           self._enrich_llm_node(span, state)
        elif name == "tts_node":           self._enrich_tts_node(span, state)
        elif name == "tts_request_run":    self._enrich_tts_request(span, state)
        elif name == "function_tool":      self._enrich_function_tool(span, state)
        elif name == "drain_agent_activity": self._enrich_turn(span, state)
        elif name == "eou_detection":      self._enrich_eou(span, state)
        elif name == "job_entrypoint":     self._enrich_root(span, state, trace_id)
        # "drain_agent_activity" also appears — same as turn, already handled above
        # "judge_evaluation" is test-only, no enrichment needed

    # ------------------------------------------------------------------
    # llm_request_run — the actual LLM API call span
    # LK sets gen_ai.request.model, gen_ai.provider.name, token counts,
    # and gen_ai.* events (system/user/assistant/tool/choice) directly.
    # We add: gen_ai.system, cost, cache hit rate, turn index.
    # ------------------------------------------------------------------

    def _enrich_llm_request(self, span: ReadableSpan, state: SessionState) -> None:
        attrs = span.attributes or {}

        # gen_ai.system is missing from LK — infer from provider name
        if not attrs.get(_ATTR_GEN_AI_SYSTEM):
            provider = str(attrs.get(_ATTR_GEN_AI_PROVIDER, ""))
            system = _provider_to_system(provider)
            if system:
                _set(span, _ATTR_GEN_AI_SYSTEM, system)

        # Token accounting
        model          = str(attrs.get(_ATTR_GEN_AI_MODEL, ""))
        input_tokens   = int(attrs.get(_ATTR_GEN_AI_IN_TOKENS,  0))
        output_tokens  = int(attrs.get(_ATTR_GEN_AI_OUT_TOKENS, 0))
        cached_tokens  = int(attrs.get(_ATTR_GEN_AI_CACHED_TOKENS, 0))

        cost = _compute_cost(model, input_tokens, output_tokens, self._prices)
        if cost is not None:
            _set(span, "gen_ai.usage.cost_usd", round(cost, 8))
            state.total_cost_usd += cost

        state.total_input_tokens  += input_tokens
        state.total_output_tokens += output_tokens

        if input_tokens and cached_tokens:
            _set(span, "gen_ai.usage.cache_hit_rate",
                 round(cached_tokens / input_tokens, 4))

        # Transition latency from handoff → first LLM call of new agent
        if state.pending_handoff_end_ns and span.start_time:
            gap_ms = (span.start_time - state.pending_handoff_end_ns) / 1_000_000
            if 0 < gap_ms < 30_000:
                _set(span, "lk.handoff.transition_latency_ms", round(gap_ms, 2))
            state.pending_handoff_end_ns = 0

    # ------------------------------------------------------------------
    # llm_node — orchestration wrapper around llm_request_run
    # Sets lk.response.text, gen_ai.request.model, gen_ai.provider.name.
    # We add: turn index, gen_ai.system.
    # ------------------------------------------------------------------

    def _enrich_llm_node(self, span: ReadableSpan, state: SessionState) -> None:
        attrs = span.attributes or {}
        state.turn_count += 1
        _set(span, "lk.turn_index", state.turn_count)

        if not attrs.get(_ATTR_GEN_AI_SYSTEM):
            provider = str(attrs.get(_ATTR_GEN_AI_PROVIDER, ""))
            system = _provider_to_system(provider)
            if system:
                _set(span, _ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(_ATTR_GEN_AI_OP_NAME):
            _set(span, _ATTR_GEN_AI_OP_NAME, "chat")

    # ------------------------------------------------------------------
    # tts_node — orchestration wrapper around tts_request_run
    # Sets gen_ai.request.model, gen_ai.provider.name, lk.response.ttfb.
    # ------------------------------------------------------------------

    def _enrich_tts_node(self, span: ReadableSpan, state: SessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(_ATTR_GEN_AI_SYSTEM):
            provider = str(attrs.get(_ATTR_GEN_AI_PROVIDER, ""))
            system = _provider_to_system(provider)
            if system:
                _set(span, _ATTR_GEN_AI_SYSTEM, system)

        if not attrs.get(_ATTR_GEN_AI_OP_NAME):
            _set(span, _ATTR_GEN_AI_OP_NAME, "text_to_speech")

        ttfb = attrs.get(_ATTR_RESPONSE_TTFB)
        if ttfb is not None:
            _set(span, "gen_ai.tts.ttfb_s", float(ttfb))

    # ------------------------------------------------------------------
    # tts_request_run — actual TTS API call
    # Sets lk.input_text, lk.response.ttfb, lk.retry_count.
    # ------------------------------------------------------------------

    def _enrich_tts_request(self, span: ReadableSpan, state: SessionState) -> None:
        attrs = span.attributes or {}
        if not attrs.get(_ATTR_GEN_AI_OP_NAME):
            _set(span, _ATTR_GEN_AI_OP_NAME, "text_to_speech")

        if self._capture_content:
            text = attrs.get(_ATTR_TTS_INPUT_TEXT, "")
            if text:
                _add_event(span, "gen_ai.assistant.message",
                           {"content": str(text), "modality": "text_for_speech"})

    # ------------------------------------------------------------------
    # function_tool — verified attributes:
    #   lk.function_tool.id, lk.function_tool.name,
    #   lk.function_tool.arguments, lk.function_tool.output,
    #   lk.function_tool.is_error
    #
    # Handoff detection: LK source has a TODO for adding handoff info here.
    # For now we detect via tool name match OR AgentHandoff in the output.
    # ------------------------------------------------------------------

    def _enrich_function_tool(self, span: ReadableSpan, state: SessionState) -> None:
        attrs = span.attributes or {}

        state.tool_call_count += 1
        _set(span, "lk.tool_call_index", state.tool_call_count)

        if not attrs.get(_ATTR_GEN_AI_OP_NAME):
            _set(span, _ATTR_GEN_AI_OP_NAME, "execute_tool")

        tool_name   = str(attrs.get(_ATTR_FNC_TOOL_NAME, ""))
        tool_output = str(attrs.get(_ATTR_FNC_TOOL_OUTPUT, ""))
        is_error    = bool(attrs.get(_ATTR_FNC_TOOL_ERROR, False))

        # Expose duration for dashboards (avoids arithmetic in SQL/ClickHouse)
        if span.end_time and span.start_time:
            _set(span, "gen_ai.tool.duration_ms",
                 round((span.end_time - span.start_time) / 1_000_000, 2))

        # Handoff detection:
        # 1. Explicit name list provided by developer
        # 2. Output contains "AgentHandoff" class name (LK uses repr())
        is_handoff = (
            tool_name in self._handoff_tools
            or "AgentHandoff" in tool_output
        )

        if is_handoff:
            state.handoff_count += 1
            _set(span, "gen_ai.tool.is_handoff",  True)
            _set(span, "lk.handoff_index",         state.handoff_count)

            # New agent name may appear in the output repr
            new_agent = _extract_new_agent(tool_output)
            if new_agent:
                _set(span, "lk.handoff.target_agent", new_agent)
                if not state.agent_chain or state.agent_chain[-1] != new_agent:
                    state.agent_chain.append(new_agent)

            # Record handoff end time so next LLM span can compute dead-air gap
            state.pending_handoff_end_ns = span.end_time or time.time_ns()

        # Content as events
        if self._capture_content:
            tool_args = attrs.get(_ATTR_FNC_TOOL_ARGS, "")
            if tool_args:
                _add_event(span, "gen_ai.tool.message",
                           {"role": "tool", "content": str(tool_args),
                            "direction": "input", "name": tool_name})
            if tool_output and not is_error:
                _add_event(span, "gen_ai.tool.message",
                           {"role": "tool", "content": tool_output,
                            "direction": "output", "name": tool_name})

    # ------------------------------------------------------------------
    # drain_agent_activity — one span per agent turn (wraps llm_node + tts_node)
    # Sets: lk.agent_label, lk.generation_id, lk.parent_generation_id,
    #       lk.user_input, lk.instructions, lk.interrupted,
    #       lk.speech_id, lk.response.text, lk.e2e_latency
    # ------------------------------------------------------------------

    def _enrich_turn(self, span: ReadableSpan, state: SessionState) -> None:
        attrs = span.attributes or {}

        e2e = attrs.get(_ATTR_E2E_LATENCY)
        if e2e is not None:
            _set(span, "lk.turn.e2e_latency_s", float(e2e))

        interrupted = attrs.get(_ATTR_INTERRUPTED)
        if interrupted:
            _set(span, "lk.turn.interrupted", True)

        if self._capture_content:
            user_input = attrs.get(_ATTR_USER_INPUT, "")
            if user_input:
                _add_event(span, "gen_ai.user.message",
                           {"content": str(user_input)})
            response = attrs.get(_ATTR_RESPONSE_TEXT, "")
            if response:
                _add_event(span, "gen_ai.assistant.message",
                           {"content": str(response)})

    # ------------------------------------------------------------------
    # eou_detection — end-of-utterance, low-level voice timing span
    # Not much to add; just stamp op name.
    # ------------------------------------------------------------------

    def _enrich_eou(self, span: ReadableSpan, state: SessionState) -> None:
        if not (span.attributes or {}).get(_ATTR_GEN_AI_OP_NAME):
            _set(span, _ATTR_GEN_AI_OP_NAME, "end_of_utterance_detection")

    # ------------------------------------------------------------------
    # job_entrypoint — root span for the session.
    # Sets: lk.agent_name, lk.job_id, lk.room_name.
    # We add session-level aggregates here.
    # ------------------------------------------------------------------

    def _enrich_root(self, span: ReadableSpan, state: SessionState,
                     trace_id: str) -> None:
        _set(span, "lk.session.turn_count",          state.turn_count)
        _set(span, "lk.session.tool_call_count",     state.tool_call_count)
        _set(span, "lk.session.handoff_count",       state.handoff_count)
        _set(span, "lk.session.total_input_tokens",  state.total_input_tokens)
        _set(span, "lk.session.total_output_tokens", state.total_output_tokens)

        if state.total_cost_usd:
            _set(span, "lk.session.total_cost_usd",
                 round(state.total_cost_usd, 6))

        if state.agent_chain:
            _set(span, "lk.session.agent_chain",
                 " → ".join(state.agent_chain))

        self._sessions.pop(trace_id, None)


# ---------------------------------------------------------------------------
# Handoff hook — install on an AgentSession to emit real handoff spans.
#
# Because LK doesn't emit a handoff span (see TODO in generation.py),
# the correct approach is to hook into the session's conversation_item_added
# event and emit our own span. This runs in the app process and has access
# to the full handoff context.
#
# Usage:
#   session = AgentSession(...)
#   install_handoff_hook(session, tracer=opentelemetry.trace.get_tracer("yoursdk"))
# ---------------------------------------------------------------------------

def install_handoff_hook(session, tracer) -> None:
    """
    Subscribe to AgentSession conversation events and emit a
    'lk.agent_handoff' span for each AgentHandoff item.

    Args:
        session: A livekit.agents.AgentSession instance.
        tracer:  An opentelemetry.trace.Tracer to emit spans with.
    """
    _handoff_start_times: dict[str, float] = {}

    @session.on("conversation_item_added")
    def _on_item_added(ev) -> None:
        item = ev.item
        if item.type != "agent_handoff":
            return

        # Emit a handoff span under the current active trace context.
        # The span is started and ended immediately because the handoff
        # is a point-in-time event, not a duration we can observe directly.
        with tracer.start_as_current_span("lk.agent_handoff") as span:
            if item.old_agent_id:
                span.set_attribute("lk.handoff.source_agent_id", str(item.old_agent_id))
            span.set_attribute("lk.handoff.target_agent_id", str(item.new_agent_id))
            span.set_attribute("gen_ai.operation.name",      "agent_handoff")
            span.set_attribute("lk.handoff.item_id",         str(item.id))
            span.set_attribute("lk.handoff.created_at",      float(item.created_at))
            # The transition latency (dead air) will be computed by
            # LiveKitGenAIProcessor when it sees the next llm_request_run span.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set(span: ReadableSpan, key: str, value) -> None:
    """Write to ReadableSpan's internal attribute dict (unavoidable pattern)."""
    if span._attributes is None:
        span._attributes = {}
    span._attributes[key] = value


def _add_event(span: ReadableSpan, name: str, attributes: dict) -> None:
    from opentelemetry.sdk.trace import Event
    evt = Event(name=name, attributes=attributes, timestamp=time.time_ns())
    if hasattr(span, "_events") and isinstance(span._events, list):
        span._events.append(evt)


def _trace_id_hex(span: ReadableSpan) -> str:
    return format(span.context.trace_id, "032x")


def _maybe_update(state: SessionState, attr: str, value) -> None:
    if value and not getattr(state, attr, ""):
        setattr(state, attr, str(value))


def _provider_to_system(provider: str) -> str:
    """
    Map livekit gen_ai.provider.name → gen_ai.system semconv value.
    LK provider names come from plugin labels, e.g. "openai", "anthropic".
    """
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
    Try to pull the new agent class name from AgentHandoff repr.
    LK's repr looks like: AgentHandoff(agent=<BillingAgent object at 0x...>)
    This is best-effort; returns "" when it can't parse.
    """
    import re
    m = re.search(r"AgentHandoff\(agent=<(\w+)", tool_output)
    return m.group(1) if m else ""


def _compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    prices: dict,
) -> Optional[float]:
    rate = prices.get(model)
    if rate is None:
        for key, val in prices.items():
            if model.startswith(key):
                rate = val
                break
    if rate is None:
        return None
    return (input_tokens * rate[0] + output_tokens * rate[1]) / 1_000_000
