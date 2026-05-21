"""Tests for platform.ref.* stamping and job context registration (LiveKit)."""

from __future__ import annotations

import asyncio

import pytest

from parlot.core.attrs import (
    ATTR_PLATFORM_FRAMEWORK,
    ATTR_PLATFORM_KIND,
    ATTR_PLATFORM_VALUE,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_SID,
)
from parlot.core.platform_refs import platform_ref_flat_key
from parlot.instrumentation.livekit._platform_refs import (
    _livekit_platform_ref_triples,
    lookup_room_context,
    register_job_context,
    register_livekit_job_context,
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
async def test_register_job_context_uses_job_room_sid() -> None:
    class _JobRoom:
        name = "demo-room"
        sid = "RM_from_job"

    class _FakeJob:
        id = "job-1"
        room = _JobRoom()

    class _HungRoom:
        name = "rtc-room"

        @property
        def sid(self):
            async def _never():
                await asyncio.sleep(3600)
                return "RM_should_not_wait"

            return _never()

    class _FakeCtx:
        job = _FakeJob()
        room = _HungRoom()
        _connected = False

    await register_job_context(_FakeCtx())
    assert lookup_room_context("job-1") == ("demo-room", "RM_from_job")


@pytest.mark.asyncio
async def test_register_job_context_rtc_fallback_when_connected() -> None:
    class _JobRoom:
        name = ""
        sid = ""

    class _FakeJob:
        id = "job-fallback"
        room = _JobRoom()

    class _RtcRoom:
        name = "rtc-name"

        @property
        def sid(self):
            async def _resolve():
                return "RM_rtc123"

            return _resolve()

    class _FakeCtx:
        job = _FakeJob()
        room = _RtcRoom()
        _connected = True

    await register_job_context(_FakeCtx())
    assert lookup_room_context("job-fallback") == ("rtc-name", "RM_rtc123")


@pytest.mark.asyncio
async def test_register_job_context_never_stores_coroutine_repr() -> None:
    class _JobRoom:
        name = "n"
        sid = ""

    class _FakeJob:
        id = "job-coro"
        room = _JobRoom()

    class _RtcRoom:
        @property
        def sid(self):
            async def _inner():
                return "RM_ok"

            return _inner()

    class _FakeCtx:
        job = _FakeJob()
        room = _RtcRoom()
        _connected = True

    await register_job_context(_FakeCtx())
    _name, sid = lookup_room_context("job-coro")
    assert "coroutine" not in sid
    assert sid == "RM_ok"
