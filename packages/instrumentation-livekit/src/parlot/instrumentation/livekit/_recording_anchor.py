"""Resolve LiveKit session recording anchor (audio_recording_started_at) when available."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parlot.instrumentation.livekit._processor import (
        LiveKitGenAIProcessor,
        _LiveKitSessionState,
    )

logger = logging.getLogger("parlot.instrumentation.livekit")


def _anchor_ms_from_unix_seconds(value: float | int | None) -> int | None:
    if value is None:
        return None
    try:
        sec = float(value)
    except (TypeError, ValueError):
        return None
    if sec <= 0:
        return None
    return int(sec * 1000)


def apply_recording_anchor_from_report(
    processor: "LiveKitGenAIProcessor",
    state: "_LiveKitSessionState",
    report: object,
) -> None:
    """Set recording anchor from a LiveKit SessionReport (no ``make_session_report`` call)."""
    if state.recording_anchor_wall_ms is not None:
        return
    started_at = getattr(report, "audio_recording_started_at", None)
    anchor_ms = _anchor_ms_from_unix_seconds(started_at)
    if anchor_ms is not None:
        processor.set_recording_anchor_wall_ms(state, anchor_ms)


def try_set_recording_anchor_from_report(
    processor: "LiveKitGenAIProcessor", state: "_LiveKitSessionState"
) -> None:
    """
    Set ``state.recording_anchor_wall_ms`` from ``ctx.session_report`` when already populated.

    Does not call ``make_session_report`` — that runs in ``on_session_end`` after RecorderIO stops.
    """
    if state.recording_anchor_wall_ms is not None:
        return
    try:
        from livekit.agents import get_job_context
    except ImportError:
        return

    try:
        ctx = get_job_context()
    except RuntimeError:
        return

    report = getattr(ctx, "session_report", None)
    if report is None:
        return

    apply_recording_anchor_from_report(processor, state, report)
