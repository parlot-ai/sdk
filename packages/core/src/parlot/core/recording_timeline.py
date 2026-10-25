"""Recording timeline helpers — sample-0 anchor and media segment math."""

from __future__ import annotations

from typing import Any, Optional, Protocol


class _HasRecordingAnchor(Protocol):
    recording_anchor_wall_ms: Optional[int]


def set_recording_anchor_wall_ms(state: Any, anchor_wall_ms: int) -> None:
    """Freeze the sample-0 wall clock on *state* (first write wins)."""
    current = getattr(state, "recording_anchor_wall_ms", None)
    if current is not None:
        return
    state.recording_anchor_wall_ms = int(anchor_wall_ms)


def media_segments_from_speech(
    state: Any,
    speech_start_wall_ms: int,
    speech_end_wall_ms: int,
) -> tuple[int, int]:
    """Return ``(start_ms, end_ms)`` offsets from the frozen recording anchor."""
    anchor = getattr(state, "recording_anchor_wall_ms", None)
    if anchor is None:
        return (0, max(0, int(speech_end_wall_ms) - int(speech_start_wall_ms)))
    start = max(0, int(speech_start_wall_ms) - int(anchor))
    end = max(start, int(speech_end_wall_ms) - int(anchor))
    return (start, end)


def speech_wall_ms_from_span(span: Any) -> tuple[int, int] | None:
    """Derive speech wall bounds from an OTel ReadableSpan start/end."""
    start_ns = getattr(span, "start_time", None)
    end_ns = getattr(span, "end_time", None)
    if start_ns is None or end_ns is None:
        return None
    try:
        start_ms = int(start_ns) // 1_000_000
        end_ms = int(end_ns) // 1_000_000
    except (TypeError, ValueError):
        return None
    if end_ms < start_ms:
        return None
    return (start_ms, end_ms)
