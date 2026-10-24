"""Pipecat session recording: stereo AudioBufferProcessor → WAV segments → /complete."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from typing import Any

from pipecat.frames.frames import CancelFrame, EndFrame
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frame_processor import FrameDirection

from parlot.core.context import ParlotContext
from parlot.core.recording import should_record as should_record_policy
from parlot.core.recording_stamp import (
    stamp_recording_disabled,
    stamp_recording_error,
    stamp_recording_started,
    stamp_recording_uploaded,
)
from parlot.core.recording_timeline import set_recording_anchor_wall_ms
from parlot.core.recording_upload import (
    complete_recording,
    fetch_upload_grant,
    grant_audio_uri,
    grant_put_url,
    put_bytes_to_presigned_url,
)
from parlot.core.session import get_active_session, get_active_session_span

from ._session import any_open_session

logger = logging.getLogger("parlot.instrumentation.pipecat.recording")

CHANNEL_MAP = "user,agent"
DEFAULT_SEGMENT_SECONDS = 30
# Mono PCM16 bytes per second at 16 kHz (AudioBufferProcessor compares per-track).
_DEFAULT_MONO_BYTES_PER_SEC = 16_000 * 2
CLOSE_TIMEOUT_S = 25.0


def _pcm_is_silent(pcm: bytes) -> bool:
    if not pcm:
        return True
    return all(b == 0 for b in pcm)


def _wav_bytes(pcm: bytes, *, sample_rate: int, num_channels: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _encode_opus_ogg(pcm: bytes, *, sample_rate: int, num_channels: int) -> bytes | None:
    """Optional Opus/OGG via PyAV (``parlot[recording-opus]`` / ``av``)."""
    try:
        import av  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        out = io.BytesIO()
        container = av.open(out, mode="w", format="ogg")
        stream = container.add_stream("libopus", rate=sample_rate)
        stream.layout = "stereo" if num_channels == 2 else "mono"
        stream.bit_rate = 32_000
        n_samples = len(pcm) // (2 * max(1, num_channels))
        if n_samples <= 0:
            return None
        frame = av.AudioFrame(
            format="s16",
            layout=stream.layout,
            samples=n_samples,
        )
        frame.sample_rate = sample_rate
        frame.planes[0].update(pcm)
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
        container.close()
        return out.getvalue()
    except Exception:
        logger.warning("parlot: Opus encode failed; falling back to WAV", exc_info=True)
        return None


class ParlotRecordingProcessor(AudioBufferProcessor):
    """Stereo buffer → ~30s WAV (or Opus) segments → presigned PUT → ``/complete``.

    Place after ``transport.output()`` so both user (L) and bot (R) audio are captured.

    Fail-open: never raises into the call path; stamps ``session.recording.status=failed``
    with a reason when capture/upload cannot complete.
    """

    def __init__(
        self,
        *,
        sample_rate: int | None = 16_000,
        segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
        format: str = "pcm_wav",
        context: ParlotContext | None = None,
        **kwargs: Any,
    ) -> None:
        mono_bytes = int(max(1.0, segment_seconds) * _DEFAULT_MONO_BYTES_PER_SEC)
        if sample_rate and sample_rate != 16_000:
            mono_bytes = int(max(1.0, segment_seconds) * sample_rate * 2)
        super().__init__(
            sample_rate=sample_rate,
            num_channels=2,
            buffer_size=mono_bytes,
            auto_start_recording=True,
            **kwargs,
        )
        self._segment_seconds = float(segment_seconds)
        self._format = "opus_ogg" if format == "opus_ogg" else "pcm_wav"
        self._context = context
        self._segment_index = 0
        self._sample_offset = 0
        self._sample_count = 0
        self._anchor_wall_ms: int | None = None
        self._audio_uri: str | None = None
        self._finished = False
        self._upload_lock = asyncio.Lock()
        self._had_non_silent = False
        self._received_audio = False

        try:
            from ._auto import register_recording_processor

            register_recording_processor(self)
        except Exception:
            pass

        @self.event_handler("on_audio_data")
        async def _on_audio(processor, audio, sample_rate, num_channels):
            try:
                await self._upload_segment(audio, sample_rate, num_channels)
            except Exception:
                logger.warning("parlot: segment upload failed", exc_info=True)
                stamp_recording_error(self._session_span(), "segment_upload_error")

        @self.event_handler("on_recording_started")
        async def _on_started(processor):
            try:
                self._maybe_stamp_started()
            except Exception:
                logger.debug("parlot: recording started stamp failed", exc_info=True)

    async def process_frame(self, frame, direction: FrameDirection):  # type: ignore[override]
        await super().process_frame(frame, direction)
        # Parent already flushed the last buffer on End/Cancel; complete upload.
        if isinstance(frame, (EndFrame, CancelFrame)):
            try:
                await self.finish()
            except Exception:
                logger.warning("parlot: recording finish on end failed", exc_info=True)

    def _runtime(self):
        ctx = self._context
        if ctx is None:
            from ._auto import configured_context

            ctx = configured_context()
        if ctx is None:
            return None
        return getattr(ctx, "runtime", None)

    def _session_span(self):
        return get_active_session_span()

    def _session_state(self):
        state = get_active_session()
        if state is not None:
            return state
        return any_open_session()

    def _session_id(self) -> str:
        state = self._session_state()
        return str(getattr(state, "session_id", "") or "") if state else ""

    def _maybe_stamp_started(self) -> None:
        if self._anchor_wall_ms is not None:
            return
        self._anchor_wall_ms = int(time.time() * 1000)
        state = self._session_state()
        if state is not None:
            set_recording_anchor_wall_ms(state, self._anchor_wall_ms)
        stamp_recording_started(
            self._session_span(),
            anchor_wall_ms=self._anchor_wall_ms,
            source="pipecat_buffer",
            channel_map=CHANNEL_MAP,
            format=self._format,
        )

    async def _upload_segment(
        self, audio: bytes, sample_rate: int, num_channels: int
    ) -> None:
        if self._finished or not audio:
            return
        async with self._upload_lock:
            await self._upload_segment_locked(audio, sample_rate, num_channels)

    async def _upload_segment_locked(
        self, audio: bytes, sample_rate: int, num_channels: int
    ) -> None:
        self._received_audio = True
        self._maybe_stamp_started()
        if not _pcm_is_silent(audio):
            self._had_non_silent = True

        runtime = self._runtime()
        session_id = self._session_id()
        if runtime is None or not session_id:
            logger.warning(
                "parlot: recording segment skipped — no runtime/session yet"
            )
            return

        content_type = "audio/ogg" if self._format == "opus_ogg" else "audio/wav"
        if self._format == "opus_ogg":
            encoded = _encode_opus_ogg(
                audio, sample_rate=sample_rate, num_channels=num_channels
            )
            if encoded is None:
                self._format = "pcm_wav"
                content_type = "audio/wav"
                body = _wav_bytes(
                    audio, sample_rate=sample_rate, num_channels=num_channels
                )
            else:
                body = encoded
        else:
            body = _wav_bytes(
                audio, sample_rate=sample_rate, num_channels=num_channels
            )

        grant = await fetch_upload_grant(
            runtime,
            session_id=session_id,
            segment_index=self._segment_index,
            sample_offset=self._sample_offset,
            content_type=content_type,
        )
        if grant is None:
            stamp_recording_error(self._session_span(), "upload_grant_failed")
            return
        put_url = grant_put_url(grant)
        if not put_url:
            stamp_recording_error(self._session_span(), "upload_grant_failed")
            return
        ok = await put_bytes_to_presigned_url(
            put_url, body, content_type=content_type
        )
        if not ok:
            stamp_recording_error(self._session_span(), "segment_put_failed")
            return

        uri = grant_audio_uri(grant)
        if uri:
            self._audio_uri = uri
        frames = len(audio) // (2 * max(1, num_channels))
        self._sample_offset += frames
        self._sample_count += frames
        self._segment_index += 1

    async def finish(self) -> None:
        """Flush last partial segment and POST ``/complete``. Fail-open."""
        if self._finished:
            return
        self._finished = True
        try:
            from ._auto import unregister_recording_processor

            unregister_recording_processor(self)
        except Exception:
            pass
        try:
            await asyncio.wait_for(self._finish_inner(), timeout=CLOSE_TIMEOUT_S)
        except asyncio.TimeoutError:
            stamp_recording_error(self._session_span(), "complete_timeout")
        except Exception as exc:
            stamp_recording_error(
                self._session_span(), f"complete_failed:{type(exc).__name__}"
            )
            logger.warning("parlot: recording finish failed — %s", exc, exc_info=True)

    async def _finish_inner(self) -> None:
        try:
            await self.stop_recording()
        except Exception:
            logger.debug("parlot: stop_recording during finish failed", exc_info=True)

        if self._segment_index == 0 and self._sample_count == 0:
            if not self._received_audio:
                stamp_recording_error(self._session_span(), "no_audio")
            else:
                stamp_recording_error(self._session_span(), "silent")
            return

        if not self._had_non_silent:
            stamp_recording_error(self._session_span(), "silent")
            return

        runtime = self._runtime()
        session_id = self._session_id()
        if runtime is None or not session_id:
            stamp_recording_error(self._session_span(), "complete_no_session")
            return

        wall_end_ms = int(time.time() * 1000)
        result = await complete_recording(
            runtime,
            session_id=session_id,
            format=self._format,
            segment_count=self._segment_index,
            sample_rate=self.sample_rate or 16_000,
            channel_map=CHANNEL_MAP,
            anchor_wall_ms=self._anchor_wall_ms,
            sample_count=self._sample_count,
            wall_end_ms=wall_end_ms,
        )
        if result is None:
            stamp_recording_error(self._session_span(), "complete_failed")
            return

        audio_uri = str(result.get("audio_recording_uri") or self._audio_uri or "")
        partial = bool(result.get("partial"))
        if audio_uri:
            stamp_recording_uploaded(
                self._session_span(),
                audio_uri=audio_uri,
                partial=partial,
                sample_count=self._sample_count,
                wall_end_ms=wall_end_ms,
                format=self._format,
            )

    async def fail(self, reason: str) -> None:
        stamp_recording_error(self._session_span(), reason)
        self._finished = True


def recording_enabled_for_agent(
    agent_id: str,
    *,
    record_config: bool | list[str] | None,
    context: ParlotContext | None,
) -> bool:
    runtime = getattr(context, "runtime", None) if context is not None else None
    agents = runtime.recording_agents_map() if runtime is not None else None
    globs = getattr(runtime, "recording_globs", None) if runtime is not None else None
    return should_record_policy(
        agent_id,
        record_config=record_config,
        bootstrap_globs=globs,
        bootstrap_agents=agents,
    )


def stamp_recording_policy_disabled(*, reason: str, span: Any = None) -> None:
    stamp_recording_disabled(
        span if span is not None else get_active_session_span(), reason
    )
