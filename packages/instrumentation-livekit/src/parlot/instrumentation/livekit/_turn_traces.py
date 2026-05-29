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
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_LABEL,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_PREV_TRACE_ID,
    ATTR_TURN_SPEECH_WALL_END_MS,
    ATTR_TURN_SPEECH_WALL_START_MS,
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
    active_agent_id: str = "",
    speech_start_wall_ms: int | None = None,
    speech_end_wall_ms: int | None = None,
    media_segment_start_ms: int = 0,
    media_segment_end_ms: int = 0,
    start_time_unix_ns: int | None = None,
    end_time_unix_ns: int | None = None,
) -> tuple[str, str]:
    """
    Start and end a ``parlot.turn`` root span in a **new** trace.

    When ``start_time_unix_ns`` / ``end_time_unix_ns`` are set (from LiveKit
    ``user_turn`` / ``agent_turn``), OTLP duration matches the speech window.

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

    start_ns = start_time_unix_ns if start_time_unix_ns is not None else None
    end_ns = end_time_unix_ns if end_time_unix_ns is not None else None

    span = tracer.start_span("parlot.turn", context=parent_ctx, start_time=start_ns)
    try:
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
        if active_agent_id:
            span.set_attribute(ATTR_TURN_ACTIVE_AGENT_ID, active_agent_id)
        if speech_start_wall_ms is not None:
            span.set_attribute(ATTR_TURN_SPEECH_WALL_START_MS, speech_start_wall_ms)
        if speech_end_wall_ms is not None:
            span.set_attribute(ATTR_TURN_SPEECH_WALL_END_MS, speech_end_wall_ms)
        if media_segment_start_ms > 0 or media_segment_end_ms > 0:
            span.set_attribute(ATTR_TURN_MEDIA_START_MS, media_segment_start_ms)
            span.set_attribute(ATTR_TURN_MEDIA_END_MS, media_segment_end_ms)
    finally:
        span.end(end_time=end_ns)

    return format(trace_id, "032x"), format(span_id, "016x")
