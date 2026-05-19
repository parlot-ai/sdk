"""
LiveKit-specific platform.ref.* registry and span stamping.

Delegates generic ``platform.ref.*`` attribute writes to
``parlot.core.platform_refs.stamp_platform_refs`` and adds ``lk.*`` legacy
keys expected by Parlot ingestion.
"""

from __future__ import annotations

import inspect

from parlot.core.attrs import (
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_NAME,
    ATTR_LK_ROOM_SID,
)
from parlot.core.platform_refs import stamp_platform_refs as _stamp_platform_refs

_FRAMEWORK_LIVEKIT = "livekit"

# job_id → (room_name, room_sid) — populated from the agent entrypoint
_job_room_context: dict[str, tuple[str, str]] = {}


def register_livekit_job_context(
    job_id: str,
    *,
    room_name: str = "",
    room_sid: str = "",
) -> None:
    """Register room metadata for a LiveKit job before spans are exported.

    Call once from the agent entrypoint (or use
    ``register_livekit_job_context_from_ctx`` if you have a ``JobContext``).
    """
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
        text = str(val).strip() if val is not None else ""
        if text:
            return text
    return ""


async def register_livekit_job_context_from_ctx(ctx) -> None:
    """Convenience: register room context from a LiveKit ``JobContext``.

    Equivalent to::

        register_livekit_job_context(
            job_id=ctx.job.id,
            room_name=ctx.room.name,
            room_sid=await ctx.room.sid,
        )

    ``room.sid`` is async in current LiveKit RTC SDKs and must be awaited.
    """
    job_id = str(getattr(ctx.job, "id", "") or "")
    room = getattr(ctx, "room", None)
    room_name = await _coerce_livekit_field(room, "name")
    room_sid = await _coerce_livekit_field(room, "sid", "id")
    register_livekit_job_context(job_id, room_name=room_name, room_sid=room_sid)
