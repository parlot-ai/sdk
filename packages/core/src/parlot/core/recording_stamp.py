"""Stamp ``session.recording.*`` attributes on an active session span."""

from __future__ import annotations

import logging
from typing import Any, Optional

from parlot.core.attrs import (
    ATTR_SESSION_RECORDING_ANCHOR_WALL_MS,
    ATTR_SESSION_RECORDING_AUDIO_URI,
    ATTR_SESSION_RECORDING_DISABLED_REASON,
    ATTR_SESSION_RECORDING_EGRESS_ID,
    ATTR_SESSION_RECORDING_FORMAT,
    ATTR_SESSION_RECORDING_PARTIAL,
    ATTR_SESSION_RECORDING_SAMPLE_COUNT,
    ATTR_SESSION_RECORDING_SOURCE,
    ATTR_SESSION_RECORDING_STATUS,
    ATTR_SESSION_RECORDING_WALL_END_MS,
    ATTR_SESSION_RECORDING_ERROR,
)

logger = logging.getLogger("parlot.core.recording_stamp")


def _span_recording(span: Any) -> bool:
    if span is None:
        return False
    if hasattr(span, "is_recording") and not span.is_recording():
        return False
    return True


def stamp_recording_attr(span: Any, key: str, value: Any) -> None:
    if not _span_recording(span):
        return
    try:
        span.set_attribute(key, value)
    except Exception:
        logger.debug("parlot: failed to stamp %s", key, exc_info=True)


def stamp_recording_disabled(span: Any, reason: str) -> None:
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_DISABLED_REASON, reason)
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_STATUS, "disabled")
    logger.debug("parlot: recording disabled — %s", reason)


def stamp_recording_error(span: Any, error: str) -> None:
    msg = error[:500]
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_ERROR, msg)
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_STATUS, "failed")
    if _span_recording(span):
        try:
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR, msg))
        except Exception:
            logger.debug("parlot: failed to set recording error span status", exc_info=True)
    # Grant denials are operational errors (Honeycomb + agent logs); keep ERROR.
    if msg.startswith(("quota_exceeded", "feature_not_granted")):
        logger.error("parlot: recording failed — %s", msg)
    else:
        logger.warning("parlot: recording failed — %s", msg)


def stamp_recording_started(
    span: Any,
    *,
    anchor_wall_ms: int,
    source: str,
    format: str = "pcm_wav",
) -> None:
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_ANCHOR_WALL_MS, int(anchor_wall_ms))
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_STATUS, "recording")
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_SOURCE, source)
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_FORMAT, format)


def stamp_recording_uploaded(
    span: Any,
    *,
    audio_uri: str,
    partial: bool = False,
    sample_count: Optional[int] = None,
    wall_end_ms: Optional[int] = None,
    format: Optional[str] = None,
    egress_id: Optional[str] = None,
) -> None:
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_AUDIO_URI, audio_uri)
    stamp_recording_attr(
        span,
        ATTR_SESSION_RECORDING_STATUS,
        "partial" if partial else "uploaded",
    )
    stamp_recording_attr(span, ATTR_SESSION_RECORDING_PARTIAL, bool(partial))
    if sample_count is not None:
        stamp_recording_attr(span, ATTR_SESSION_RECORDING_SAMPLE_COUNT, int(sample_count))
    if wall_end_ms is not None:
        stamp_recording_attr(span, ATTR_SESSION_RECORDING_WALL_END_MS, int(wall_end_ms))
    if format:
        stamp_recording_attr(span, ATTR_SESSION_RECORDING_FORMAT, format)
    if egress_id:
        stamp_recording_attr(span, ATTR_SESSION_RECORDING_EGRESS_ID, egress_id)
