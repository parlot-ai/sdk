"""Tests for platform.ref.* stamping and job room registry (LiveKit)."""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace import TracerProvider

from parlot.core.attrs import (
    ATTR_PLATFORM_FRAMEWORK,
    ATTR_PLATFORM_KIND,
    ATTR_PLATFORM_VALUE,
)
from parlot.core.platform_refs import platform_ref_flat_key
from parlot.instrumentation.livekit._platform_refs import (
    _job_room_context,
    _livekit_platform_ref_triples,
    lookup_room_context,
    register_livekit_job_context,
    stamp_livekit_platform_refs,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import refresh_bootstrap_room_from_ctx
from bootstrap_helpers import bootstrap_via_agent_state


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
    assert span._attributes[platform_ref_flat_key("room_sid")] == "RM_test"
    assert span._attributes[platform_ref_flat_key("job_id")] == "job-1"
    assert span._attributes[platform_ref_flat_key("room_name")] == "demo"


def test_stamp_skipped_when_no_ids() -> None:
    span = _FakeSpan()
    stamp_livekit_platform_refs(span)
    assert span._attributes == {}


@pytest.mark.asyncio
async def test_refresh_bootstrap_room_from_job_assignment() -> None:
    _job_room_context.clear()

    class _JobRoom:
        name = "pre-connect-room"
        sid = "RM_pre"

    class _FakeJob:
        id = "job-pre"
        room = _JobRoom()

    class _FakeCtx:
        job = _FakeJob()
        room = None
        _connected = False

    proc = LiveKitGenAIProcessor()
    provider = TracerProvider()
    provider.add_span_processor(proc)
    proc.set_tracer(provider.get_tracer("test"))
    bootstrap_via_agent_state(proc, "job-pre")

    await refresh_bootstrap_room_from_ctx(_FakeCtx())
    assert lookup_room_context("job-pre") == ("pre-connect-room", "RM_pre")
    _job_room_context.clear()


@pytest.mark.asyncio
async def test_refresh_bootstrap_prefers_job_room_sid_over_rtc() -> None:
    _job_room_context.clear()

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

    proc = LiveKitGenAIProcessor()
    provider = TracerProvider()
    provider.add_span_processor(proc)
    proc.set_tracer(provider.get_tracer("test"))
    bootstrap_via_agent_state(proc, "job-1")

    await refresh_bootstrap_room_from_ctx(_FakeCtx())
    assert lookup_room_context("job-1") == ("demo-room", "RM_from_job")
    _job_room_context.clear()


@pytest.mark.asyncio
async def test_refresh_bootstrap_rtc_fallback_when_connected() -> None:
    _job_room_context.clear()

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

    proc = LiveKitGenAIProcessor()
    provider = TracerProvider()
    provider.add_span_processor(proc)
    proc.set_tracer(provider.get_tracer("test"))
    bootstrap_via_agent_state(proc, "job-fallback")

    await refresh_bootstrap_room_from_ctx(_FakeCtx())
    assert lookup_room_context("job-fallback") == ("rtc-name", "RM_rtc123")
    _job_room_context.clear()
