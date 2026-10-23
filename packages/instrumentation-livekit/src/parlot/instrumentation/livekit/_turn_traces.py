"""Emit per-turn OTel root spans (new trace_id each turn) for Parlot ingest."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from parlot.core.attrs import (
    ATTR_PARTICIPANT_DIAR_SOURCE,
    ATTR_TURN_ACTIVE_AGENT_ID,
    ATTR_TURN_EOU_DELAY_S,
    ATTR_TURN_INPUT_MODALITY,
    ATTR_TURN_LANGUAGE,
    ATTR_TURN_LANGUAGE_SWITCH,
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_PARTICIPANT_ID,
    ATTR_TURN_PARTICIPANT_LABEL,
    ATTR_TURN_SPEECH_WALL_END_MS,
    ATTR_TURN_SPEECH_WALL_START_MS,
    ATTR_TURN_TRANSCRIPTION_DELAY_S,
)
from parlot.core.turn_emit import emit_parlot_turn_root

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
    e2e_latency_s: float | None = None,
    llm_ttft_s: float | None = None,
    tts_ttfb_s: float | None = None,
    transcription_delay_s: float | None = None,
    eou_delay_s: float | None = None,
    interrupted: bool = False,
    language: str = "",
    language_switch: str = "",
    utterance_text: str = "",
) -> tuple[str, str]:
    """
    Start and end a ``parlot.turn`` root span in a **new** trace.

    When ``start_time_unix_ns`` / ``end_time_unix_ns`` are set (from LiveKit
    ``user_turn`` / ``agent_turn``), OTLP duration matches the speech window.

    Returns ``(trace_id, span_id)`` as 32- and 16-char hex strings.
    """
    extra: dict[str, Any] = {}
    if participant_id:
        extra[ATTR_TURN_PARTICIPANT_ID] = participant_id
    if participant_label:
        extra[ATTR_TURN_PARTICIPANT_LABEL] = participant_label
    if diarization_source:
        extra[ATTR_PARTICIPANT_DIAR_SOURCE] = diarization_source
    if input_modality:
        extra[ATTR_TURN_INPUT_MODALITY] = input_modality
    if active_agent_id:
        extra[ATTR_TURN_ACTIVE_AGENT_ID] = active_agent_id
    if speech_start_wall_ms is not None:
        extra[ATTR_TURN_SPEECH_WALL_START_MS] = speech_start_wall_ms
    if speech_end_wall_ms is not None:
        extra[ATTR_TURN_SPEECH_WALL_END_MS] = speech_end_wall_ms
    if media_segment_start_ms > 0 or media_segment_end_ms > 0:
        extra[ATTR_TURN_MEDIA_START_MS] = media_segment_start_ms
        extra[ATTR_TURN_MEDIA_END_MS] = media_segment_end_ms
    if transcription_delay_s is not None:
        extra[ATTR_TURN_TRANSCRIPTION_DELAY_S] = transcription_delay_s
    if eou_delay_s is not None:
        extra[ATTR_TURN_EOU_DELAY_S] = eou_delay_s
    if language:
        extra[ATTR_TURN_LANGUAGE] = language
    if language_switch:
        extra[ATTR_TURN_LANGUAGE_SWITCH] = language_switch

    return emit_parlot_turn_root(
        tracer,
        session_id=session_id,
        conversation_id=conversation_id,
        turn_index=turn_index,
        participant_role=participant_role,
        utterance_text=utterance_text,
        prev_trace_id=prev_trace_id,
        start_time_unix_ns=start_time_unix_ns,
        end_time_unix_ns=end_time_unix_ns,
        interrupted=interrupted,
        e2e_latency_s=e2e_latency_s,
        llm_ttft_s=llm_ttft_s,
        tts_ttfb_s=tts_ttfb_s,
        extra_attrs=extra,
    )
