"""
LiveKit-specific platform.ref.* registry and span stamping.

Delegates generic ``platform.ref.*`` attribute writes to
``parlot.core.platform_refs.stamp_platform_refs`` and adds ``lk.*`` legacy
keys expected by Parlot ingestion.
"""

from __future__ import annotations

import inspect
import logging

from parlot.core.attrs import (
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
)
from parlot.core.platform_refs import stamp_platform_refs as _stamp_platform_refs

logger = logging.getLogger("parlot.instrumentation.livekit")

_FRAMEWORK_LIVEKIT = "livekit"

# job_id → (room_name, room_sid) — populated from the agent entrypoint
_job_room_context: dict[str, tuple[str, str]] = {}


def register_livekit_job_context(
    job_id: str,
    *,
    room_name: str = "",
    room_sid: str = "",
) -> None:
    """Register room metadata for a LiveKit job (internal; used by the processor)."""
    if not job_id:
        return
    _job_room_context[job_id] = (room_name or "", room_sid or "")


def clear_livekit_job_context(job_id: str) -> None:
    """Remove the registration for a completed job (called by the processor)."""
    _job_room_context.pop(job_id, None)


def lookup_room_context(job_id: str) -> tuple[str, str]:
    """Return (room_name, room_sid) for a job, or ("", "") if unknown."""
    return _job_room_context.get(job_id, ("", ""))


def _livekit_platform_ref_triples(
    *,
    job_id: str = "",
    room_name: str = "",
    room_sid: str = "",
) -> list[tuple[str, str, str]]:
    """Return (framework, kind, value) tuples for stamping as span attributes."""
    refs: list[tuple[str, str, str]] = []
    if room_sid:
        refs.append((_FRAMEWORK_LIVEKIT, "room_sid", room_sid))
    if job_id:
        refs.append((_FRAMEWORK_LIVEKIT, "job_id", job_id))
    if room_name:
        refs.append((_FRAMEWORK_LIVEKIT, "room_name", room_name))
    return refs


def stamp_livekit_platform_refs(
    span,
    *,
    job_id: str = "",
    room_name: str = "",
    room_sid: str = "",
) -> None:
    """Stamp primary ``platform.ref.*`` triple plus ``lk.*`` legacy keys on a span."""
    triples = _livekit_platform_ref_triples(
        job_id=job_id, room_name=room_name, room_sid=room_sid
    )
    if not triples:
        return
    _stamp_platform_refs(span, triples)

    if span._attributes is None:
        span._attributes = {}

    for _fw, kind, val in triples:
        if kind == "room_sid":
            span._attributes[ATTR_LK_ROOM_SID] = val
        elif kind == "job_id":
            span._attributes[ATTR_LK_JOB_ID] = val
        elif kind == "room_name":
            span._attributes[ATTR_LK_ROOM_NAME] = val


def _str_field(obj, *attr_names: str) -> str:
    """Read a plain string field without awaiting (protobuf / sync attrs)."""
    if obj is None:
        return ""
    for name in attr_names:
        try:
            val = getattr(obj, name, None)
        except Exception:
            continue
        if val is None or inspect.isawaitable(val):
            continue
        if callable(val) and not isinstance(val, type):
            continue
        text = str(val).strip()
        if text:
            return text
    return ""


async def _coerce_livekit_field(obj, *attr_names: str) -> str:
    """Read a string field from a LiveKit object, awaiting async properties."""
    if obj is None:
        return ""
    for name in attr_names:
        try:
            val = getattr(obj, name, None)
        except Exception:
            continue
        if val is None:
            continue
        if inspect.isawaitable(val):
            val = await val
        elif callable(val) and not isinstance(val, type):
            try:
                called = val()
            except TypeError:
                continue
            if inspect.isawaitable(called):
                val = await called
            else:
                val = called
        if inspect.isawaitable(val):
            logger.debug(
                "Skipping un-awaited LiveKit field %s on %r", name, type(obj).__name__
            )
            continue
        text = str(val).strip() if val is not None else ""
        if text and "coroutine" not in text:
            return text
    return ""


def _job_room_fields(ctx) -> tuple[str, str, str]:
    """Sync fields from job assignment (safe before ``ctx.connect()``)."""
    job_id = str(getattr(ctx.job, "id", "") or "")
    job_room = getattr(ctx.job, "room", None)
    room_name = _str_field(job_room, "name")
    room_sid = _str_field(job_room, "sid")
    if not room_name:
        room_name = _str_field(getattr(ctx, "room", None), "name")
    return job_id, room_name, room_sid


async def register_job_context(ctx) -> None:
    """Register room metadata from a LiveKit ``JobContext``.

    Call once per job, after ``await ctx.connect()``::

        await ctx.connect()
        await register_job_context(ctx)

    Uses ``ctx.job.room.sid`` from the job assignment (sync). Only falls back to
    ``await ctx.room.sid`` when the job protobuf has no SID and the room is
    already connected.
    """
    job_id, room_name, room_sid = _job_room_fields(ctx)

    if not room_sid and getattr(ctx, "_connected", False):
        room = getattr(ctx, "room", None)
        room_sid = await _coerce_livekit_field(room, "sid", "id")
        if not room_name:
            room_name = await _coerce_livekit_field(room, "name")

    register_livekit_job_context(job_id, room_name=room_name, room_sid=room_sid)
