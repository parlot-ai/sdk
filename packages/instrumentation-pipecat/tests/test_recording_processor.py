"""Unit tests for ParlotRecordingProcessor helpers and BYO stamp."""

from __future__ import annotations

import wave
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parlot.core.recording_source import stamp_external_recording
from parlot.instrumentation.pipecat._recording import (
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
