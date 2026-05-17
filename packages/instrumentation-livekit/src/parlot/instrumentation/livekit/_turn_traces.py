"""Emit per-turn OTel root spans (new trace_id each turn) for Parlot ingest."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from parlot.core.attrs import (
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_INDEX,
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
) -> str:
    """
    Start and immediately end a ``parlot.turn`` root span in a **new** trace.

    Returns the new trace_id (32-char hex).
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

    return format(trace_id, "032x")
