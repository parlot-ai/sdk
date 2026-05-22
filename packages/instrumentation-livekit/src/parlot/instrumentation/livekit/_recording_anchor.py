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


def try_set_recording_anchor_from_report(
    processor: "LiveKitGenAIProcessor", state: "_LiveKitSessionState"
) -> None:
    """
    Set ``state.recording_anchor_wall_ms`` from LiveKit SessionReport when the
    job context exposes ``audio_recording_started_at``.
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
        make_report = getattr(ctx, "make_session_report", None)
        if callable(make_report):
            try:
                report = make_report()
            except Exception:
                logger.debug("parlot: make_session_report failed", exc_info=True)
                return

    if report is None:
        return

    started_at = getattr(report, "audio_recording_started_at", None)
    anchor_ms = _anchor_ms_from_unix_seconds(started_at)
    if anchor_ms is not None:
        processor.set_recording_anchor_wall_ms(state, anchor_ms)
