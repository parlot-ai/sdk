"""Parlot upload-grant + recording-complete HTTP clients."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import httpx

from parlot.core.runtime import ParlotRuntimeContext

logger = logging.getLogger("parlot.core.recording_upload")

_SESSION_RECORDINGS_GRANT = "session_recordings"
_GRANT_DENIAL_CODES = frozenset({"quota_exceeded", "feature_not_granted"})


@dataclass(frozen=True)
class UploadGrantOutcome:
    """Result of ``/v1/recordings/upload-grant``.

    On success ``grant`` is the JSON body. On failure ``error`` is a durable
    ``recording_error`` string (e.g. ``quota_exceeded:session_recordings``).
    """

    grant: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.grant is not None


def recording_grant_error(
    code: str, *, grant_type: str = _SESSION_RECORDINGS_GRANT
) -> str:
    """Canonical recording_error for session_recordings grant denials."""
    return f"{code}:{grant_type}"


def _parse_upload_grant_error(status_code: int, body_text: str) -> str:
    """Map HTTP error body to a durable recording_error code."""
    code = ""
    grant_type = _SESSION_RECORDINGS_GRANT
    try:
        data = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, dict):
        raw = data.get("error") or data.get("code") or ""
        if isinstance(raw, str):
            code = raw.strip()
        gt = data.get("grant_type")
        if isinstance(gt, str) and gt.strip():
            grant_type = gt.strip()
    if code in _GRANT_DENIAL_CODES:
        return recording_grant_error(code, grant_type=grant_type)
    if status_code in (403, 429) and not code:
        guessed = "quota_exceeded" if status_code == 429 else "feature_not_granted"
        return recording_grant_error(guessed, grant_type=grant_type)
    return "upload_grant_failed"


async def fetch_upload_grant(
    runtime: ParlotRuntimeContext,
    *,
    session_id: str,
    room_name: Optional[str] = None,
    segment_index: Optional[int] = None,
    sample_offset: Optional[int] = None,
    content_type: Optional[str] = None,
) -> UploadGrantOutcome:
    """POST ``/v1/recordings/upload-grant``; return grant body or structured error."""
    url = f"{runtime.endpoint.rstrip('/')}/v1/recordings/upload-grant"
    headers = {"Authorization": f"Bearer {runtime.api_key}"}
    payload: dict[str, Any] = {"session_id": session_id}
    if room_name:
        payload["room_name"] = room_name
    if segment_index is not None:
        payload["segment_index"] = int(segment_index)
    if sample_offset is not None:
        payload["sample_offset"] = int(sample_offset)
    if content_type:
        payload["content_type"] = content_type
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            error = _parse_upload_grant_error(resp.status_code, resp.text[:500])
            logger.error(
                "parlot: upload grant failed status=%s error=%s body=%s",
                resp.status_code,
                error,
                resp.text[:500],
            )
            return UploadGrantOutcome(error=error)
        data = resp.json()
        if isinstance(data, dict):
            return UploadGrantOutcome(grant=data)
        return UploadGrantOutcome(error="upload_grant_failed")
    except Exception as exc:
        logger.error("parlot: upload grant request failed — %s", exc)
        logger.debug("parlot: upload grant request failed", exc_info=True)
        return UploadGrantOutcome(error="upload_grant_failed")


async def complete_recording(
    runtime: ParlotRuntimeContext,
    *,
    session_id: str,
    format: str,
    conversation_id: Optional[str] = None,
    segment_count: Optional[int] = None,
    segments: Optional[Sequence[Mapping[str, int]]] = None,
    sample_rate: Optional[int] = None,
    anchor_wall_ms: Optional[int] = None,
    sample_count: Optional[int] = None,
    wall_end_ms: Optional[int] = None,
    duration_ms: Optional[int] = None,
    audio_recording_uri: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """POST ``/v1/recordings/complete``; return JSON body or ``None`` on failure."""
    url = f"{runtime.endpoint.rstrip('/')}/v1/recordings/complete"
    headers = {"Authorization": f"Bearer {runtime.api_key}"}
    payload: dict[str, Any] = {
        "session_id": session_id,
        "format": format,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if segment_count is not None:
        payload["segment_count"] = int(segment_count)
    if segments:
        payload["segments"] = [
            {
                "segment_index": int(s["segment_index"]),
                "sample_offset": int(s["sample_offset"]),
            }
            for s in segments
        ]
    if sample_rate is not None:
        payload["sample_rate"] = int(sample_rate)
    if anchor_wall_ms is not None:
        payload["anchor_wall_ms"] = int(anchor_wall_ms)
    if sample_count is not None:
        payload["sample_count"] = int(sample_count)
    if wall_end_ms is not None:
        payload["wall_end_ms"] = int(wall_end_ms)
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    if audio_recording_uri:
        payload["audio_recording_uri"] = audio_recording_uri
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error(
                "parlot: recording complete failed status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.error("parlot: recording complete failed — %s", exc)
        logger.debug("parlot: recording complete failed", exc_info=True)
        return None


async def put_bytes_to_presigned_url(
    put_url: str,
    body: bytes,
    *,
    content_type: str = "audio/wav",
    timeout: float = 120.0,
) -> bool:
    """PUT object bytes to a presigned URL. Returns True on 2xx."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.put(
                put_url,
                content=body,
                headers={"Content-Type": content_type},
            )
        if resp.status_code >= 400:
            logger.error(
                "parlot: presigned PUT failed status=%s body=%s",
                resp.status_code,
                resp.text[:300],
            )
            return False
        return True
    except Exception as exc:
        logger.error("parlot: presigned PUT failed — %s", exc)
        logger.debug("parlot: presigned PUT failed", exc_info=True)
        return False


def grant_put_url(grant: Mapping[str, Any] | None) -> Optional[str]:
    if not grant:
        return None
    url = grant.get("put_url")
    return str(url) if isinstance(url, str) and url.strip() else None


def grant_audio_uri(grant: Mapping[str, Any] | None) -> Optional[str]:
    if not grant:
        return None
    uri = grant.get("audio_recording_uri")
    return str(uri) if isinstance(uri, str) and uri.strip() else None
