"""Unit tests for recording upload clients, timeline math, and BYO stamp."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parlot.core.attrs import ATTR_SESSION_RECORDING_STATUS
from parlot.core.recording_source import stamp_external_recording
from parlot.core.recording_stamp import stamp_recording_started, stamp_recording_uploaded
from parlot.core.recording_timeline import (
    media_segments_from_speech,
    set_recording_anchor_wall_ms,
    speech_wall_ms_from_span,
)
from parlot.core.recording_upload import (
    complete_recording,
    fetch_upload_grant,
    grant_put_url,
    put_bytes_to_presigned_url,
)
from parlot.core.runtime import ParlotRuntimeContext


def _runtime() -> ParlotRuntimeContext:
    return ParlotRuntimeContext(
        endpoint="https://ingest.example",
        api_key="pk_test",
        tenant_id="org",
        content_bucket="b",
        r2_endpoint="https://r2.example",
    )


def test_set_recording_anchor_first_write_wins() -> None:
    state = SimpleNamespace(recording_anchor_wall_ms=None)
    set_recording_anchor_wall_ms(state, 1000)
    set_recording_anchor_wall_ms(state, 9999)
    assert state.recording_anchor_wall_ms == 1000


def test_media_segments_from_speech() -> None:
    state = SimpleNamespace(recording_anchor_wall_ms=1_000_000)
    assert media_segments_from_speech(state, 1_000_500, 1_001_000) == (500, 1000)


def test_speech_wall_ms_from_span() -> None:
    span = SimpleNamespace(
        start_time=1_000_000_000_000,
        end_time=1_500_000_000_000,
    )
    assert speech_wall_ms_from_span(span) == (1_000_000, 1_500_000)


def test_stamp_external_link_rejected_when_pii_required() -> None:
    span = MagicMock()
    span.is_recording.return_value = True
    ok = stamp_external_recording(
        audio_uri="https://cdn.example/call.ogg",
        anchor_wall_ms=1,
        mode="link",
        pii_redaction_required=True,
        span=span,
    )
    assert ok is False
    span.set_attribute.assert_any_call(
        ATTR_SESSION_RECORDING_STATUS,
        "failed",
    )


def test_stamp_external_link_ok() -> None:
    span = MagicMock()
    span.is_recording.return_value = True
    ok = stamp_external_recording(
        audio_uri="https://cdn.example/call.ogg",
        anchor_wall_ms=42,
        mode="link",
        span=span,
    )
    assert ok is True


def test_stamp_recording_uploaded_partial() -> None:
    span = MagicMock()
    span.is_recording.return_value = True
    stamp_recording_started(
        span, anchor_wall_ms=1, source="pipecat_buffer", format="pcm_wav"
    )
    stamp_recording_uploaded(
        span, audio_uri="r2://b/k", partial=True, sample_count=100, wall_end_ms=2
    )
    keys = [c.args[0] for c in span.set_attribute.call_args_list]
    assert ATTR_SESSION_RECORDING_STATUS in keys


@pytest.mark.asyncio
async def test_fetch_upload_grant_posts_segment() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"put_url": "https://put", "audio_recording_uri": "r2://x"}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(return_value=resp)
    with patch("parlot.core.recording_upload.httpx.AsyncClient", return_value=client):
        grant = await fetch_upload_grant(
            _runtime(),
            session_id="s1",
            segment_index=3,
            sample_offset=48000,
            content_type="audio/wav",
        )
    assert grant_put_url(grant) == "https://put"
    payload = client.post.call_args.kwargs["json"]
    assert payload["segment_index"] == 3
    assert payload["sample_offset"] == 48000


@pytest.mark.asyncio
async def test_complete_recording_posts_body() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True, "partial": False}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(return_value=resp)
    with patch("parlot.core.recording_upload.httpx.AsyncClient", return_value=client):
        out = await complete_recording(
            _runtime(),
            session_id="s1",
            format="pcm_wav",
            conversation_id="conv-1",
            segment_count=2,
            segments=[
                {"segment_index": 0, "sample_offset": 0},
                {"segment_index": 1, "sample_offset": 16000},
            ],
            sample_rate=16000,
            anchor_wall_ms=1,
            sample_count=32000,
            wall_end_ms=2000,
        )
    assert out == {"ok": True, "partial": False}
    body = client.post.await_args.kwargs["json"]
    assert body["conversation_id"] == "conv-1"
    assert body["segments"] == [
        {"segment_index": 0, "sample_offset": 0},
        {"segment_index": 1, "sample_offset": 16000},
    ]


@pytest.mark.asyncio
async def test_put_bytes_success() -> None:
    resp = MagicMock()
    resp.status_code = 200
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.put = AsyncMock(return_value=resp)
    with patch("parlot.core.recording_upload.httpx.AsyncClient", return_value=client):
        assert await put_bytes_to_presigned_url("https://put", b"RIFF") is True
