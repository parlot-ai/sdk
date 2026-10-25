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


def _schedule_upload(proc, audio: bytes, sample_rate: int = 16000, num_channels: int = 1):
    """Mirror on_audio_data: child task registered for finish() drain."""
    import asyncio

    task = asyncio.create_task(
        proc._upload_segment(audio, sample_rate, num_channels),
        name="parlot-recording-upload",
    )
    proc._upload_tasks.add(task)
    task.add_done_callback(proc._upload_tasks.discard)
    return task


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

    async def slow_locked(audio: bytes, sample_rate: int, num_channels: int) -> None:
        # Real _upload_segment acquires the lock + checks _finished before this.
        proc._received_audio = True
        proc._had_non_silent = True
        started.set()
        await release.wait()
        proc._uploaded_segments.append({"segment_index": 0, "sample_offset": 0})
        proc._sample_count = 1600
        proc._sample_offset = 1600
        proc._segment_index = 1

    with (
        patch.object(proc, "stop_recording", new_callable=AsyncMock),
        patch.object(proc, "_upload_segment_locked", side_effect=slow_locked),
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
        upload_task = _schedule_upload(proc, b"\x01\x00" * 100)
        await started.wait()
        finish_task = asyncio.create_task(proc.finish())
        # Drain blocks on the registered upload task (no timing sleep).
        for _ in range(20):
            if not finish_task.done() and err.call_count == 0:
                await asyncio.sleep(0)
            else:
                break
        assert not finish_task.done()
        err.assert_not_called()
        release.set()
        await finish_task
        await upload_task

    complete.assert_awaited_once()
    err.assert_not_called()
    assert complete.await_args.kwargs["segment_count"] == 1


@pytest.mark.asyncio
async def test_finish_rejects_upload_after_drain_before_complete() -> None:
    """Upload window closes after drain so late flushes cannot orphan raw/."""
    import asyncio

    from parlot.instrumentation.pipecat._recording import ParlotRecordingProcessor

    proc = ParlotRecordingProcessor(segment_seconds=1)
    proc._cached_session_id = "s" * 32
    proc._cached_runtime = MagicMock(endpoint="http://localhost:8788", api_key="k")
    proc._anchor_wall_ms = 1
    proc._segment_index = 1
    proc._uploaded_segments = [{"segment_index": 0, "sample_offset": 0}]
    proc._sample_count = 1600
    proc._had_non_silent = True
    proc._received_audio = True

    gate_closed = asyncio.Event()
    complete_release = asyncio.Event()
    late_committed = False

    async def slow_complete(*_a, **_k):
        gate_closed.set()
        await complete_release.wait()
        return {"audio_recording_uri": "r2://b/audio.ogg", "partial": False}

    async def late_locked(audio: bytes, sample_rate: int, num_channels: int) -> None:
        nonlocal late_committed
        late_committed = True
        proc._segment_index += 1

    with (
        patch.object(proc, "stop_recording", new_callable=AsyncMock),
        patch(
            "parlot.instrumentation.pipecat._recording.complete_recording",
            side_effect=slow_complete,
        ) as complete,
        patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_uploaded"
        ),
        patch.object(proc, "_upload_segment_locked", side_effect=late_locked),
    ):
        finish_task = asyncio.create_task(proc.finish())
        await gate_closed.wait()
        assert proc._finished is True
        await proc._upload_segment(b"\x01\x00" * 100, 16000, 1)
        assert late_committed is False
        assert proc._segment_index == 1
        complete_release.set()
        await finish_task

    complete.assert_awaited_once()
    assert complete.await_args.kwargs["segment_count"] == 1


@pytest.mark.asyncio
async def test_finish_cancel_awaits_same_task_once() -> None:
    """CancelledError must not start a second _finish_inner / /complete."""
    import asyncio

    from parlot.instrumentation.pipecat._recording import ParlotRecordingProcessor

    proc = ParlotRecordingProcessor(segment_seconds=1)
    proc._cached_session_id = "s" * 32
    proc._cached_runtime = MagicMock(endpoint="http://localhost:8788", api_key="k")
    proc._anchor_wall_ms = 1
    proc._segment_index = 1
    proc._uploaded_segments = [{"segment_index": 0, "sample_offset": 0}]
    proc._sample_count = 1600
    proc._had_non_silent = True
    proc._received_audio = True

    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[int] = []

    async def slow_complete(*_a, **_k):
        calls.append(1)
        entered.set()
        await release.wait()
        return {"audio_recording_uri": "r2://b/audio.ogg", "partial": False}

    with (
        patch.object(proc, "stop_recording", new_callable=AsyncMock),
        patch(
            "parlot.instrumentation.pipecat._recording.complete_recording",
            side_effect=slow_complete,
        ),
        patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_uploaded"
        ),
    ):
        finish_task = asyncio.create_task(proc.finish())
        await entered.wait()
        finish_task.cancel()
        # Unblock /complete so the shielded inner task can finish; finish() awaits it.
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await finish_task

    assert calls == [1]
    assert proc._finished is True


@pytest.mark.asyncio
async def test_finish_upload_drain_timeout_proceeds() -> None:
    """Hung PUT must not consume the whole /complete budget."""
    import asyncio

    from parlot.instrumentation.pipecat import _recording as rec_mod
    from parlot.instrumentation.pipecat._recording import ParlotRecordingProcessor

    proc = ParlotRecordingProcessor(segment_seconds=1)
    proc._cached_session_id = "s" * 32
    proc._cached_runtime = MagicMock(endpoint="http://localhost:8788", api_key="k")
    proc._anchor_wall_ms = 1

    started = asyncio.Event()

    async def hung_locked(audio: bytes, sample_rate: int, num_channels: int) -> None:
        proc._received_audio = True
        proc._had_non_silent = True
        started.set()
        await asyncio.Event().wait()  # never completes

    with (
        patch.object(rec_mod, "UPLOAD_DRAIN_TIMEOUT_S", 0.05),
        patch.object(proc, "stop_recording", new_callable=AsyncMock),
        patch.object(proc, "_upload_segment_locked", side_effect=hung_locked),
        patch(
            "parlot.instrumentation.pipecat._recording.stamp_recording_error"
        ) as err,
    ):
        upload_task = _schedule_upload(proc, b"\x01\x00" * 100)
        await started.wait()
        await proc.finish()
        upload_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await upload_task

    # Zero committed segments + non-silent → segment_upload_error (not silent).
    err.assert_called()
    assert err.call_args.args[1] == "segment_upload_error"
    assert proc._finished is True


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
