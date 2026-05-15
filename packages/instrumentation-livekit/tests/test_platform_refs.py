"""Tests for platform.ref.* stamping and job context registration (LiveKit)."""

from __future__ import annotations

from parlot.instrumentation.livekit._platform_refs import (
    _livekit_platform_ref_triples,
    lookup_room_context,
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
    assert span._attributes["platform.ref.framework"] == "livekit"
    assert span._attributes["platform.ref.kind"] == "room_sid"
    assert span._attributes["platform.ref.value"] == "RM_test"
    assert span._attributes["lk.room.sid"] == "RM_test"
    assert span._attributes["lk.job_id"] == "job-1"
    assert span._attributes["platform.ref.room_name"] == "demo"


def test_stamp_skipped_when_no_ids() -> None:
    span = _FakeSpan()
    stamp_livekit_platform_refs(span)
    assert span._attributes == {}
