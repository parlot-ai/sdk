"""Framework-agnostic recording source protocol + BYO helpers."""

from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

from parlot.core.recording_stamp import (
    stamp_recording_error,
    stamp_recording_started,
    stamp_recording_uploaded,
)
from parlot.core.session import get_active_session_span

logger = logging.getLogger("parlot.core.recording_source")


@runtime_checkable
class RecordingSource(Protocol):
    """Adapter-facing recording capture / stamp contract."""

    async def start(self) -> None: ...

    async def finish(self) -> None: ...

    async def fail(self, reason: str) -> None: ...


def stamp_external_recording(
    *,
    audio_uri: str,
    anchor_wall_ms: int,
    mode: str = "link",
    format: str = "opus_ogg",
    sample_count: Optional[int] = None,
    wall_end_ms: Optional[int] = None,
    pii_redaction_required: bool = False,
    span: Any = None,
) -> bool:
    """BYO recording stamp.

    * ``mode="link"`` — external URI only. Rejected when *pii_redaction_required*.
    * ``mode="ingest"`` — caller already uploaded via grant; stamp as uploaded.

    Returns False when rejected or no session span.
    """
    target = span if span is not None else get_active_session_span()
    if target is None:
        logger.warning("parlot: stamp_external_recording skipped — no session span")
        return False

    if mode == "link" and pii_redaction_required:
        stamp_recording_error(
            target,
            "byo_link_rejected:tenant_pii_redaction_enabled",
        )
        return False

    source = "byo_link" if mode == "link" else "byo_ingest"
    stamp_recording_started(
        target,
        anchor_wall_ms=anchor_wall_ms,
        source=source,
        format=format,
    )
    stamp_recording_uploaded(
        target,
        audio_uri=audio_uri,
        partial=False,
        sample_count=sample_count,
        wall_end_ms=wall_end_ms,
        format=format,
    )
    return True
