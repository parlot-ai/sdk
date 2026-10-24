"""Parlot upload-grant + recording-complete HTTP clients."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

import httpx

from parlot.core.runtime import ParlotRuntimeContext

logger = logging.getLogger("parlot.core.recording_upload")


async def fetch_upload_grant(
    runtime: ParlotRuntimeContext,
    *,
    session_id: str,
    room_name: Optional[str] = None,
    segment_index: Optional[int] = None,
    sample_offset: Optional[int] = None,
    content_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """POST ``/v1/recordings/upload-grant``; return JSON body or ``None`` on failure."""
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
            logger.error(
                "parlot: upload grant failed status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.error("parlot: upload grant request failed — %s", exc)
        logger.debug("parlot: upload grant request failed", exc_info=True)
        return None


async def complete_recording(
    runtime: ParlotRuntimeContext,
    *,
    session_id: str,
    format: str,
    conversation_id: Optional[str] = None,
    segment_count: Optional[int] = None,
    segments: Optional[list[Mapping[str, int]]] = None,
    sample_rate: Optional[int] = None,
    channel_map: Optional[str] = None,
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
    if channel_map:
        payload["channel_map"] = channel_map
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
        logger.error("parlot: recording complete request failed — %s", exc)
        logger.debug("parlot: recording complete request failed", exc_info=True)
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


def grant_put_url(grant: Mapping[str, Any]) -> Optional[str]:
    url = grant.get("put_url")
    return str(url) if isinstance(url, str) and url.strip() else None


def grant_audio_uri(grant: Mapping[str, Any]) -> Optional[str]:
    uri = grant.get("audio_recording_uri")
    return str(uri) if isinstance(uri, str) and uri.strip() else None
