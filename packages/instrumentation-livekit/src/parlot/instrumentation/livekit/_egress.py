"""LiveKit Room Composite egress → Cloudflare R2 via Parlot upload grant."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from parlot.core.attrs import (
    ATTR_SESSION_AUDIO_RECORDING_URI,
    ATTR_SESSION_RECORDING_ANCHOR_WALL_MS,
)
from parlot.core.runtime import get_runtime

from parlot.instrumentation.livekit.attrs import ATTR_SESSION_EGRESS_ID

from ._recording_guard import should_record
from ._runtime_context import get_livekit_runtime

logger = logging.getLogger("parlot.instrumentation.livekit")


async def _fetch_upload_grant(session_id: str, room_name: str) -> Optional[dict]:
    runtime = get_runtime()
    if runtime is None:
        logger.error("parlot: upload grant requested without runtime bootstrap")
        return None
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
    if not should_record(ctx):
        return

    runtime = get_runtime()
    lk_runtime = get_livekit_runtime()
    if runtime is None or lk_runtime is None:
        logger.error("parlot: egress skipped — bootstrap not loaded")
        return

    if not lk_runtime.webhook_signing_key or not runtime.egress_webhook_url:
        logger.error("parlot: egress skipped — webhook config missing from bootstrap")
        return

    from parlot.instrumentation.livekit._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    if bootstrap is None:
        logger.warning("parlot: egress skipped — no active job bootstrap")
        return

    room = getattr(ctx, "room", None)
    room_name = getattr(room, "name", None) or getattr(ctx, "room_name", None)
    if not room_name:
        logger.warning("parlot: egress skipped — room name unavailable")
        return

    session_id = bootstrap.session_id
    grant = await _fetch_upload_grant(session_id, str(room_name))
    if grant is None:
        return

    s3 = grant.get("s3") or {}
    filepath = grant.get("filepath") or ""
    audio_uri = grant.get("audio_recording_uri") or ""

    try:
        from livekit import api
    except ImportError:
        logger.error("parlot: livekit-api not available for egress")
        return

    lk_url = __import__("os").environ.get("LIVEKIT_URL", "")
    lk_key = __import__("os").environ.get("LIVEKIT_API_KEY", "")
    lk_secret = __import__("os").environ.get("LIVEKIT_API_SECRET", "")
    if not (lk_url and lk_key and lk_secret):
        logger.error("parlot: LIVEKIT_* env required to start egress")
        return

    file_output = api.EncodedFileOutput(
        file_type=api.EncodedFileType.OGG,
        filepath=filepath,
        disable_manifest=True,
        s3=api.S3Upload(
            access_key=str(s3.get("access_key") or ""),
            secret=str(s3.get("secret") or ""),
            bucket=str(s3.get("bucket") or ""),
            endpoint=str(s3.get("endpoint") or ""),
            force_path_style=bool(s3.get("force_path_style", True)),
        ),
    )

    webhook = api.WebhookConfig(
        url=runtime.egress_webhook_url,
        signing_key=lk_runtime.webhook_signing_key,
    )

    req = api.RoomCompositeEgressRequest(
        room_name=str(room_name),
        audio_only=True,
        file_outputs=[file_output],
        webhooks=[webhook],
    )

    lkapi = api.LiveKitAPI(lk_url, lk_key, lk_secret)
    try:
        info = await lkapi.egress.start_room_composite_egress(req)
    except Exception:
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
                session_span.set_attribute(ATTR_SESSION_AUDIO_RECORDING_URI, audio_uri)
            session_span.set_attribute(ATTR_SESSION_RECORDING_ANCHOR_WALL_MS, anchor_ms)
            if egress_id:
                session_span.set_attribute(ATTR_SESSION_EGRESS_ID, str(egress_id))

    bootstrap.processor.set_recording_anchor_wall_ms(bootstrap.state, anchor_ms)
    logger.info(
        "parlot: started room composite egress egress_id=%s uri=%s",
        egress_id,
        audio_uri,
    )
