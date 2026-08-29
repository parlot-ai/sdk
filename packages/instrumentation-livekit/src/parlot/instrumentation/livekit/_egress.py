"""LiveKit Room Composite egress → Cloudflare R2 via Parlot upload grant."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from parlot.core.attrs import (
    ATTR_SESSION_RECORDING_ANCHOR_WALL_MS,
    ATTR_SESSION_RECORDING_AUDIO_URI,
    ATTR_SESSION_RECORDING_DISABLED_REASON,
    ATTR_SESSION_RECORDING_EGRESS_ID,
    ATTR_SESSION_RECORDING_WEBHOOK_ERROR,
)
from parlot.core.context import ParlotContext
from parlot.core.runtime import ParlotRuntimeContext

from ._recording_guard import recording_disabled_reason, should_record

logger = logging.getLogger("parlot.instrumentation.livekit")


def _format_egress_error(exc: BaseException) -> str:
    """Normalize LiveKit Twirp/API errors for session.recording.webhook_error."""
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None) or str(exc)
    if code and message:
        return f"{code}: {message}"[:500]
    if code:
        return str(code)[:500]
    return message[:500] if message else "egress_start_failed"


def _stamp_recording_webhook_error(bootstrap: Any, error: str) -> None:
    """Surface recording failure on parlot.session (copied to parlot.session.close)."""
    session_span = bootstrap.session_span
    if session_span is not None and hasattr(session_span, "is_recording"):
        if session_span.is_recording():
            session_span.set_attribute(ATTR_SESSION_RECORDING_WEBHOOK_ERROR, error)
    logger.warning("parlot: recording failed — %s", error)


def _stamp_recording_disabled(bootstrap: Any, reason: str) -> None:
    """Record why egress was not started (Settings / configure / job metadata)."""
    session_span = bootstrap.session_span
    if session_span is not None and hasattr(session_span, "is_recording"):
        if session_span.is_recording():
            session_span.set_attribute(ATTR_SESSION_RECORDING_DISABLED_REASON, reason)
    logger.debug("parlot: recording disabled — %s", reason)


def _context_from_bootstrap(bootstrap: Any) -> ParlotContext | None:
    processor = getattr(bootstrap, "processor", None)
    return getattr(processor, "_context", None) if processor is not None else None


async def _fetch_upload_grant(
    session_id: str,
    room_name: str,
    runtime: ParlotRuntimeContext,
) -> Optional[dict]:
    url = f"{runtime.endpoint}/v1/recordings/upload-grant"
    headers = {"Authorization": f"Bearer {runtime.api_key}"}
    payload = {"session_id": session_id, "room_name": room_name}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error(
                "parlot: upload grant failed status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            return None
        return resp.json()
    except Exception:
        logger.exception("parlot: upload grant request failed")
        return None


async def maybe_start_room_composite_egress(ctx: Any) -> None:
    """Start OGG room composite egress to R2 when recording policy allows."""
    from parlot.instrumentation.livekit._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    context = _context_from_bootstrap(bootstrap) if bootstrap is not None else None
    if not should_record(ctx, context=context):
        if bootstrap is not None:
            _stamp_recording_disabled(
                bootstrap, recording_disabled_reason(ctx, context=context)
            )
        return

    if bootstrap is None:
        logger.warning("parlot: egress skipped — no active job bootstrap")
        return

    runtime = context.runtime if context is not None else None
    if runtime is None:
        _stamp_recording_webhook_error(bootstrap, "egress_config_missing: bootstrap")
        logger.error("parlot: egress skipped — bootstrap not loaded")
        return

    room = getattr(ctx, "room", None)
    room_name = getattr(room, "name", None) or getattr(ctx, "room_name", None)
    if not room_name:
        _stamp_recording_webhook_error(bootstrap, "egress_no_room_name")
        logger.warning("parlot: egress skipped — room name unavailable")
        return

    session_id = bootstrap.session_id
    grant = await _fetch_upload_grant(session_id, str(room_name), runtime)
    if grant is None:
        _stamp_recording_webhook_error(bootstrap, "upload_grant_failed")
        return

    s3 = grant.get("s3") or {}
    filepath = grant.get("filepath") or ""
    audio_uri = grant.get("audio_recording_uri") or ""

    s3_kwargs: dict[str, object] = {
        "access_key": str(s3.get("access_key") or ""),
        "secret": str(s3.get("secret") or ""),
        "bucket": str(s3.get("bucket") or ""),
        "endpoint": str(s3.get("endpoint") or ""),
        "force_path_style": bool(s3.get("force_path_style", True)),
    }
    session_token = s3.get("session_token")
    if session_token:
        s3_kwargs["session_token"] = str(session_token)

    try:
        from livekit import api
    except ImportError:
        _stamp_recording_webhook_error(bootstrap, "livekit_api_unavailable")
        logger.error("parlot: livekit-api not available for egress")
        return

    lk_url = __import__("os").environ.get("LIVEKIT_URL", "")
    lk_key = __import__("os").environ.get("LIVEKIT_API_KEY", "")
    lk_secret = __import__("os").environ.get("LIVEKIT_API_SECRET", "")
    if not (lk_url and lk_key and lk_secret):
        _stamp_recording_webhook_error(bootstrap, "livekit_credentials_missing")
        logger.error("parlot: LIVEKIT_* env required to start egress")
        return

    file_output = api.EncodedFileOutput(
        file_type=api.EncodedFileType.OGG,
        filepath=filepath,
        disable_manifest=True,
        s3=api.S3Upload(**s3_kwargs),
    )

    req = api.RoomCompositeEgressRequest(
        room_name=str(room_name),
        audio_only=True,
        file_outputs=[file_output],
    )

    lkapi = api.LiveKitAPI(lk_url, lk_key, lk_secret)
    try:
        info = await lkapi.egress.start_room_composite_egress(req)
    except Exception as exc:
        _stamp_recording_webhook_error(bootstrap, _format_egress_error(exc))
        logger.exception("parlot: StartRoomCompositeEgress failed")
        return
    finally:
        await lkapi.aclose()

    egress_id = getattr(info, "egress_id", None) or getattr(info, "egressId", None) or ""
    anchor_ms = int(time.time() * 1000)

    session_span = bootstrap.session_span
    if session_span is not None and hasattr(session_span, "is_recording"):
        if session_span.is_recording():
            if audio_uri:
                session_span.set_attribute(ATTR_SESSION_RECORDING_AUDIO_URI, audio_uri)
            session_span.set_attribute(ATTR_SESSION_RECORDING_ANCHOR_WALL_MS, anchor_ms)
            if egress_id:
                session_span.set_attribute(ATTR_SESSION_RECORDING_EGRESS_ID, str(egress_id))

    bootstrap.processor.set_recording_anchor_wall_ms(bootstrap.state, anchor_ms)
    logger.info(
        "parlot: started room composite egress egress_id=%s uri=%s",
        egress_id,
        audio_uri,
    )
