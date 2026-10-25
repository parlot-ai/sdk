"""Pipecat session recording: mixed dual-mono stereo → WAV segments → /complete."""

from __future__ import annotations

import array
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

DEFAULT_SEGMENT_SECONDS = 30
# Mono PCM16 bytes per second at 16 kHz (AudioBufferProcessor compares per-track).
_DEFAULT_MONO_BYTES_PER_SEC = 16_000 * 2
# Must cover stop_recording flush + POST /complete (httpx timeout 120s). Local
# stitch of multi‑MB WAV segments often exceeds 25s and used to abort mid-complete.
CLOSE_TIMEOUT_S = 120.0


def _pcm_is_silent(pcm: bytes) -> bool:
    if not pcm:
        return True
    return all(b == 0 for b in pcm)


def _mono_pcm_to_dual_stereo(pcm: bytes) -> bytes:
    """Duplicate mono s16le onto L and R (LiveKit-style mixed stereo, not L/R split)."""
    mono = array.array("h")
    mono.frombytes(pcm)
    stereo = array.array("h")
    for sample in mono:
        stereo.append(sample)
        stereo.append(sample)
    return stereo.tobytes()


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
    """Mixed dual-mono stereo → ~30s WAV (or Opus) segments → presigned PUT → ``/complete``.

    Place after ``transport.output()`` so user and bot are buffered. Pipecat mixes
    both tracks (``num_channels=1``); we expand to stereo with the same mix on L and R
    so playback matches LiveKit Room Composite rather than hard-panned L/R.

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
        # Mono merge in Pipecat (not user-L / bot-R); we dual-mono to stereo on upload.
        super().__init__(
            sample_rate=sample_rate,
            num_channels=1,
            buffer_size=mono_bytes,
            auto_start_recording=True,
            **kwargs,
        )
        self._segment_seconds = float(segment_seconds)
        self._format = "opus_ogg" if format == "opus_ogg" else "pcm_wav"
        self._context = context
        self._segment_index = 0
        self._uploaded_segments: list[dict[str, int]] = []
        self._sample_offset = 0
        self._sample_count = 0
        self._anchor_wall_ms: int | None = None
        self._audio_uri: str | None = None
        self._finished = False
        self._upload_lock = asyncio.Lock()
        self._had_non_silent = False
        self._received_audio = False
        # Cached so /complete still works after CancelFrame tears down the session.
        self._cached_session_id: str = ""
        self._cached_conversation_id: str = ""
        self._cached_runtime: Any = None
        self._cached_session_span: Any = None

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
        # Complete *before* End/Cancel propagate: pushing CancelFrame ends the
        # Pipecat conversation span, which calls close_session and clears the
        # active session — finish() would then skip /complete (no session id).
        if isinstance(frame, (EndFrame, CancelFrame)):
            try:
                await self.finish()
            except Exception:
                logger.warning("parlot: recording finish on end failed", exc_info=True)
            await super().process_frame(frame, direction)
            return
        await super().process_frame(frame, direction)

    def _runtime(self):
        if self._cached_runtime is not None:
            return self._cached_runtime
        ctx = self._context
        if ctx is None:
            from ._auto import configured_context

            ctx = configured_context()
        if ctx is None:
            return None
        return getattr(ctx, "runtime", None)

    def _session_span(self):
        span = get_active_session_span()
        if span is not None:
            self._cached_session_span = span
            return span
        return self._cached_session_span

    def _session_state(self):
        state = get_active_session()
        if state is not None:
            return state
        return any_open_session()

    def _session_id(self) -> str:
        state = self._session_state()
        sid = str(getattr(state, "session_id", "") or "") if state else ""
        if sid:
            self._cached_session_id = sid
            return sid
        return self._cached_session_id

    def _cache_binding(self) -> None:
        runtime = self._runtime()
        if runtime is not None:
            self._cached_runtime = runtime
        sid = self._session_id()
        if sid:
            self._cached_session_id = sid
        state = self._session_state()
        cid = str(getattr(state, "conversation_id", "") or "") if state else ""
        if cid:
            self._cached_conversation_id = cid
        span = get_active_session_span()
        if span is not None:
            self._cached_session_span = span

    def _maybe_stamp_started(self) -> None:
        if self._anchor_wall_ms is not None:
            return
        self._anchor_wall_ms = int(time.time() * 1000)
        self._cache_binding()
        state = self._session_state()
        if state is not None:
            set_recording_anchor_wall_ms(state, self._anchor_wall_ms)
        stamp_recording_started(
            self._session_span(),
            anchor_wall_ms=self._anchor_wall_ms,
            source="pipecat_buffer",
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
        self._cache_binding()
        if not _pcm_is_silent(audio):
            self._had_non_silent = True

        runtime = self._cached_runtime or self._runtime()
        session_id = self._cached_session_id or self._session_id()
        if runtime is None or not session_id:
            logger.warning(
                "parlot: recording segment skipped — no runtime/session yet"
            )
            return

        # Timeline frames from the buffer (mono mix); encode as dual-mono stereo.
        frames = len(audio) // (2 * max(1, num_channels))
        pcm = (
            _mono_pcm_to_dual_stereo(audio)
            if num_channels == 1
            else audio
        )
        out_channels = 2 if num_channels == 1 else num_channels

        content_type = "audio/ogg" if self._format == "opus_ogg" else "audio/wav"
        if self._format == "opus_ogg":
            encoded = _encode_opus_ogg(
                pcm, sample_rate=sample_rate, num_channels=out_channels
            )
            if encoded is None:
                self._format = "pcm_wav"
                content_type = "audio/wav"
                body = _wav_bytes(
                    pcm, sample_rate=sample_rate, num_channels=out_channels
                )
            else:
                body = encoded
        else:
            body = _wav_bytes(
                pcm, sample_rate=sample_rate, num_channels=out_channels
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
        self._uploaded_segments.append(
            {
                "segment_index": self._segment_index,
                "sample_offset": self._sample_offset,
            }
        )
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
            await asyncio.shield(
                asyncio.wait_for(self._finish_inner(), timeout=CLOSE_TIMEOUT_S)
            )
        except asyncio.TimeoutError:
            stamp_recording_error(self._session_span(), "complete_timeout")
        except asyncio.CancelledError:
            # Pipeline cancel can interrupt us; still try to complete once.
            try:
                await self._finish_inner()
            except Exception as exc:
                stamp_recording_error(
                    self._session_span(), f"complete_failed:{type(exc).__name__}"
                )
            raise
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

        runtime = self._cached_runtime or self._runtime()
        session_id = self._cached_session_id or self._session_id()
        if runtime is None or not session_id:
            stamp_recording_error(self._session_span(), "complete_no_session")
            logger.warning(
                "parlot: recording complete skipped — no session "
                "(cached_id=%r)",
                self._cached_session_id,
            )
            return

        wall_end_ms = int(time.time() * 1000)
        logger.info(
            "parlot: recording complete session_id=%s segments=%s samples=%s",
            session_id,
            self._segment_index,
            self._sample_count,
        )
        conversation_id = self._cached_conversation_id
        if not conversation_id:
            state = self._session_state()
            conversation_id = (
                str(getattr(state, "conversation_id", "") or "") if state else ""
            )
        result = await complete_recording(
            runtime,
            session_id=session_id,
            format=self._format,
            conversation_id=conversation_id or None,
            segment_count=self._segment_index,
            segments=list(self._uploaded_segments),
            sample_rate=self.sample_rate or 16_000,
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
