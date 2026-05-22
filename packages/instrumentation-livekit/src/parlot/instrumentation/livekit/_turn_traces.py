"""Emit per-turn OTel root spans (new trace_id each turn) for Parlot ingest."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from parlot.core.attrs import (
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_ACTIVE_AGENT_ID,
    ATTR_TURN_INDEX,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_INTENT_KEY,
    ATTR_TURN_INTENT_LABEL,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_LABEL,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_PREV_TRACE_ID,
)

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer


def emit_turn_root_span(
    tracer: "Tracer",
    *,
    session_id: str,
    conversation_id: str,
    turn_index: int,
    prev_trace_id: str = "",
    participant_role: str = "",
    participant_id: str = "",
    participant_label: str = "",
    diarization_source: str = "",
    input_modality: str = "",
    intent_label: str = "",
    intent_key: str = "",
    active_agent_id: str = "",
) -> tuple[str, str]:
    """
    Start and immediately end a ``parlot.turn`` root span in a **new** trace.

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
    parent = NonRecordingSpan(ctx)
    parent_ctx = trace.set_span_in_context(parent)

    with tracer.start_as_current_span("parlot.turn", context=parent_ctx) as span:
        span.set_attribute(ATTR_SESSION_ID, session_id)
        span.set_attribute(ATTR_SESSION_CONVERSATION_ID, conversation_id)
        span.set_attribute(ATTR_TURN_INDEX, turn_index)
        if prev_trace_id:
            span.set_attribute(ATTR_TURN_PREV_TRACE_ID, prev_trace_id)
        if participant_role:
            span.set_attribute(ATTR_TURN_PARTICIPANT_ROLE, participant_role)
        if participant_id:
            span.set_attribute(ATTR_TURN_PARTICIPANT_ID, participant_id)
        if participant_label:
            span.set_attribute(ATTR_TURN_PARTICIPANT_LABEL, participant_label)
        if diarization_source:
            span.set_attribute(ATTR_PARTICIPANT_DIAR_SOURCE, diarization_source)
        if input_modality:
            span.set_attribute(ATTR_TURN_INPUT_MODALITY, input_modality)
        if intent_label:
            span.set_attribute(ATTR_TURN_INTENT_LABEL, intent_label)
        if intent_key:
            span.set_attribute(ATTR_TURN_INTENT_KEY, intent_key)
        if active_agent_id:
            span.set_attribute(ATTR_TURN_ACTIVE_AGENT_ID, active_agent_id)

    return format(trace_id, "032x"), format(span_id, "016x")
