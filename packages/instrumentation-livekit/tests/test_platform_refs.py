"""Tests for platform.ref.* stamping and job context registration (LiveKit)."""

from __future__ import annotations

import pytest

from parlot.core.attrs import (
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_SID,
    ATTR_PLATFORM_FRAMEWORK,
    ATTR_PLATFORM_KIND,
    ATTR_PLATFORM_VALUE,
)
from parlot.core.platform_refs import platform_ref_flat_key
from parlot.instrumentation.livekit._platform_refs import (
    _livekit_platform_ref_triples,
    lookup_room_context,
    register_livekit_job_context,
    register_livekit_job_context_from_ctx,
    stamp_livekit_platform_refs,
)


class _FakeSpan:
    def __init__(self) -> None:
        self._attributes: dict | None = {}


def test_platform_ref_triples_orders_room_sid_first() -> None:
    triples = _livekit_platform_ref_triples(
        job_id="job-1",
        room_name="my-room",
        room_sid="RM_abc123",
    )
    assert triples[0] == ("livekit", "room_sid", "RM_abc123")
    assert ("livekit", "job_id", "job-1") in triples
    assert ("livekit", "room_name", "my-room") in triples


def test_register_livekit_job_context_lookup() -> None:
    register_livekit_job_context("job-99", room_name="demo", room_sid="RM_xyz")
    assert lookup_room_context("job-99") == ("demo", "RM_xyz")
    assert lookup_room_context("missing") == ("", "")


def test_stamp_livekit_platform_refs() -> None:
    span = _FakeSpan()
    stamp_livekit_platform_refs(
        span,
        job_id="job-1",
        room_name="demo",
        room_sid="RM_test",
    )
    assert span._attributes[ATTR_PLATFORM_FRAMEWORK] == "livekit"
    assert span._attributes[ATTR_PLATFORM_KIND] == "room_sid"
    assert span._attributes[ATTR_PLATFORM_VALUE] == "RM_test"
    assert span._attributes[ATTR_LK_ROOM_SID] == "RM_test"
    assert span._attributes[ATTR_LK_JOB_ID] == "job-1"
    assert span._attributes[platform_ref_flat_key("room_name")] == "demo"


def test_stamp_skipped_when_no_ids() -> None:
    span = _FakeSpan()
    stamp_livekit_platform_refs(span)
    assert span._attributes == {}


@pytest.mark.asyncio
async def test_register_from_ctx_awaits_async_room_sid() -> None:
    class _FakeRoom:
        name = "demo-room"

        @property
        def sid(self):
            async def _resolve():
                return "RM_async123"

            return _resolve()

    class _FakeJob:
        id = "job-async"

    class _FakeCtx:
        job = _FakeJob()
        room = _FakeRoom()

    await register_livekit_job_context_from_ctx(_FakeCtx())
    assert lookup_room_context("job-async") == ("demo-room", "RM_async123")
