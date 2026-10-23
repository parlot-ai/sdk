"""Shared helpers for minting and stamping ``parlot.turn`` root spans."""

from __future__ import annotations

import random
from typing import Any, Callable, Mapping

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from parlot.core.attrs import (
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_E2E_LATENCY_S,
    ATTR_TURN_INDEX,
    ATTR_TURN_INTERRUPTED,
    ATTR_TURN_LLM_TTFT_S,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_PREV_TRACE_ID,
    ATTR_TURN_TTS_TTFB_S,
    ATTR_TURN_USER_TEXT,
    SPAN_PARLOT_TURN,
)


def stamp_turn_utterance_text(
    span: Any,
    *,
    participant_role: str,
    utterance_text: str,
) -> None:
    """
    Stamp ``turn.user_text`` or ``turn.agent_text`` on a turn root span.

    Adapters call this after committing an utterance so the OTLP contract stays
    consistent regardless of source.
    """
    text = (utterance_text or "").strip()
    if not text:
        return
    role = (participant_role or "").strip().lower()
    if role == "user":
        span.set_attribute(ATTR_TURN_USER_TEXT, text)
    elif role == "agent":
        span.set_attribute(ATTR_TURN_AGENT_TEXT, text)


def emit_parlot_turn_root(
    tracer: Any,
    *,
    session_id: str,
    conversation_id: str,
    turn_index: int,
    participant_role: str = "",
    utterance_text: str = "",
    user_text: str = "",
    agent_text: str = "",
    prev_trace_id: str = "",
    start_time_unix_ns: int | None = None,
    end_time_unix_ns: int | None = None,
    interrupted: bool = False,
    e2e_latency_s: float | None = None,
    llm_ttft_s: float | None = None,
    tts_ttfb_s: float | None = None,
    stamp_genai_conversation_id: bool = False,
    extra_attrs: Mapping[str, Any] | None = None,
    stamp_fn: Callable[[Any], None] | None = None,
) -> tuple[str, str]:
    """
    Start and end a ``parlot.turn`` root span in a **new** OTel trace.

    When ``start_time_unix_ns`` / ``end_time_unix_ns`` are set, OTLP duration
    matches the speech / turn window.

    Prefer explicit ``user_text`` / ``agent_text`` when both sides of an exchange
    are known; otherwise pass ``utterance_text`` with ``participant_role``.

    ``extra_attrs`` carries framework-specific turn attributes (media ms,
    diarization, ``agent.framework``, etc.). ``stamp_fn`` runs before the span
    ends (platform refs, framework identity).

    Returns ``(trace_id, span_id)`` as 32- and 16-char hex strings.
    """
    trace_id = random.getrandbits(128)
    span_id = random.getrandbits(64)
    ctx = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(0x01),
    )
    parent_ctx = trace.set_span_in_context(NonRecordingSpan(ctx))

    start_kw: dict[str, Any] = {"context": parent_ctx}
    if start_time_unix_ns is not None:
        start_kw["start_time"] = start_time_unix_ns

    span = tracer.start_span(SPAN_PARLOT_TURN, **start_kw)
    try:
        span.set_attribute(ATTR_SESSION_ID, session_id)
        span.set_attribute(ATTR_SESSION_CONVERSATION_ID, conversation_id)
        if stamp_genai_conversation_id:
            span.set_attribute(ATTR_GEN_AI_CONVERSATION_ID, conversation_id)
        span.set_attribute(ATTR_TURN_INDEX, turn_index)
        if participant_role:
            span.set_attribute(ATTR_TURN_PARTICIPANT_ROLE, participant_role)
        if prev_trace_id:
            span.set_attribute(ATTR_TURN_PREV_TRACE_ID, prev_trace_id)
        if interrupted:
            span.set_attribute(ATTR_TURN_INTERRUPTED, True)
        if e2e_latency_s is not None:
            span.set_attribute(ATTR_TURN_E2E_LATENCY_S, float(e2e_latency_s))
        if llm_ttft_s is not None:
            span.set_attribute(ATTR_TURN_LLM_TTFT_S, float(llm_ttft_s))
        if tts_ttfb_s is not None:
            span.set_attribute(ATTR_TURN_TTS_TTFB_S, float(tts_ttfb_s))

        user = (user_text or "").strip()
        agent = (agent_text or "").strip()
        if user or agent:
            if user:
                stamp_turn_utterance_text(
                    span, participant_role="user", utterance_text=user
                )
            if agent:
                stamp_turn_utterance_text(
                    span, participant_role="agent", utterance_text=agent
                )
        elif utterance_text:
            stamp_turn_utterance_text(
                span,
                participant_role=participant_role,
                utterance_text=utterance_text,
            )

        if extra_attrs:
            for key, value in extra_attrs.items():
                if value is None or value == "":
                    continue
                span.set_attribute(key, value)
        if stamp_fn is not None:
            stamp_fn(span)
    finally:
        if end_time_unix_ns is not None:
            span.end(end_time=end_time_unix_ns)
        else:
            span.end()

    return format(trace_id, "032x"), format(span_id, "016x")
