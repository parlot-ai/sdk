"""Unit tests for ParlotRecordingProcessor helpers and BYO stamp."""

from __future__ import annotations

import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parlot.core.recording_source import stamp_external_recording
from parlot.instrumentation.pipecat._recording import (
    _mono_pcm_to_dual_stereo,
    _pcm_is_silent,
    _wav_bytes,
    recording_enabled_for_agent,
)


def test_wav_bytes_roundtrip() -> None:
    pcm = b"\x01\x00" * 160  # 80 stereo frames of tiny samples
    wav = _wav_bytes(pcm, sample_rate=16000, num_channels=2)
    with wave.open(BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 16000
        assert wf.readframes(wf.getnframes()) == pcm


def test_mono_to_dual_stereo_duplicates_channels() -> None:
    # Three mono s16 samples → interleaved L=R
    mono = b"\x01\x00\x02\x00\x03\x00"
    stereo = _mono_pcm_to_dual_stereo(mono)
    assert stereo == b"\x01\x00\x01\x00\x02\x00\x02\x00\x03\x00\x03\x00"


def test_pcm_silence_detection() -> None:
    assert _pcm_is_silent(b"")
    assert _pcm_is_silent(b"\x00\x00" * 10)
    assert not _pcm_is_silent(b"\x01\x00")


def test_recording_enabled_for_agent() -> None:
    assert recording_enabled_for_agent(
        "bot", record_config=True, context=None
    )
    assert not recording_enabled_for_agent(
        "bot", record_config=False, context=None
    )
    assert recording_enabled_for_agent(
        "bot-a", record_config=["bot-*"], context=None
    )


def test_byo_link_rejects_pii() -> None:
    span = MagicMock()
    span.is_recording.return_value = True
    assert (
        stamp_external_recording(
            audio_uri="https://ex/a.ogg",
            anchor_wall_ms=1,
            mode="link",
            pii_redaction_required=True,
            span=span,
        )
        is False
    )


@pytest.mark.asyncio
async def test_finish_no_audio_stamps_failed() -> None:
    from parlot.instrumentation.pipecat._recording import ParlotRecordingProcessor

    proc = ParlotRecordingProcessor(segment_seconds=1)
    with patch.object(proc, "stop_recording", new_callable=AsyncMock):
        with patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_error"
        ) as err:
            await proc.finish()
            err.assert_called()
            assert err.call_args.args[1] == "no_audio"


@pytest.mark.asyncio
async def test_finish_waits_for_in_flight_upload_before_silent_check() -> None:
    """Regression: cancel must not stamp silent while the final segment PUT runs."""
    import asyncio

    from parlot.instrumentation.pipecat._recording import ParlotRecordingProcessor

    proc = ParlotRecordingProcessor(segment_seconds=1)
    proc._cached_session_id = "s" * 32
    proc._cached_runtime = MagicMock(endpoint="http://localhost:8788", api_key="k")
    proc._anchor_wall_ms = 1

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_upload(audio: bytes, sample_rate: int, num_channels: int) -> None:
        proc._begin_upload()
        try:
            async with proc._upload_lock:
                proc._received_audio = True
                proc._had_non_silent = True
                started.set()
                await release.wait()
                proc._uploaded_segments.append(
                    {"segment_index": 0, "sample_offset": 0}
                )
                proc._sample_count = 1600
                proc._sample_offset = 1600
                proc._segment_index = 1
        finally:
            proc._end_upload()

    with (
        patch.object(proc, "stop_recording", new_callable=AsyncMock),
        patch.object(proc, "_upload_segment", side_effect=slow_upload),
        patch(
            "parlot.instrumentation.pipecat._recording.complete_recording",
            new_callable=AsyncMock,
            return_value={
                "audio_recording_uri": "r2://b/audio.ogg",
                "partial": False,
            },
        ) as complete,
        patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_error"
        ) as err,
        patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_uploaded"
        ),
    ):
        # Simulate stop_recording flush kicking off an in-flight upload.
        upload_task = asyncio.create_task(
            proc._upload_segment(b"\x01\x00" * 100, 16000, 1)
        )
        await started.wait()
        finish_task = asyncio.create_task(proc.finish())
        # finish must block in drain — not stamp silent yet
        await asyncio.sleep(0.05)
        assert not finish_task.done()
        err.assert_not_called()
        release.set()
        await finish_task
        await upload_task

    complete.assert_awaited_once()
    err.assert_not_called()
    assert complete.await_args.kwargs["segment_count"] == 1


@pytest.mark.asyncio
async def test_finish_uses_cached_session_after_clear() -> None:
    """CancelFrame clears the active session before a late finish; cache must win."""
    from parlot.instrumentation.pipecat._recording import ParlotRecordingProcessor

    proc = ParlotRecordingProcessor(segment_seconds=1)
    proc._cached_session_id = "s" * 32
    proc._cached_runtime = MagicMock(endpoint="http://localhost:8788", api_key="k")
    proc._segment_index = 2
    proc._uploaded_segments = [
        {"segment_index": 0, "sample_offset": 0},
        {"segment_index": 1, "sample_offset": 500},
    ]
    proc._sample_count = 1000
    proc._had_non_silent = True
    proc._received_audio = True
    proc._anchor_wall_ms = 1
    with (
        patch.object(proc, "stop_recording", new_callable=AsyncMock),
        patch(
            "parlot.instrumentation.pipecat._recording.complete_recording",
            new_callable=AsyncMock,
            return_value={
                "audio_recording_uri": "r2://b/audio.ogg",
                "partial": False,
            },
        ) as complete,
        patch(
            "parlot.instrumentation.pipecat._recording.get_active_session",
            return_value=None,
        ),
        patch(
            "parlot.instrumentation.pipecat._recording.any_open_session",
            return_value=None,
        ),
        patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_uploaded"
        ),
    ):
        await proc.finish()
    complete.assert_awaited_once()
    assert complete.await_args.kwargs["session_id"] == "s" * 32
    assert complete.await_args.kwargs["segment_count"] == 2
    assert complete.await_args.kwargs["segments"] == [
        {"segment_index": 0, "sample_offset": 0},
        {"segment_index": 1, "sample_offset": 500},
    ]
