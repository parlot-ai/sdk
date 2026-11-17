"""Fail-open helpers when Parlot OTLP ingest returns HTTP 429."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger("parlot.core.otlp_quota")

_quota_logged = False
_quota_lock = threading.Lock()


def reset_parlot_quota_log_for_tests() -> None:
    """Clear the process-wide quota warning latch (tests only)."""
    global _quota_logged
    with _quota_lock:
        _quota_logged = False


def _parse_error_body(body_text: str) -> dict[str, Any]:
    try:
        data = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def log_parlot_ingest_quota_once(
    *,
    channel: str,
    status_code: int,
    body_text: str,
) -> None:
    """Emit at most one quota warning per process."""
    global _quota_logged
    with _quota_lock:
        if _quota_logged:
            return
        _quota_logged = True

    body = _parse_error_body(body_text)
    error = body.get("error") or body.get("code") or "quota_exceeded"
    parts = [
        f"Parlot {channel} ingest quota exceeded (HTTP {status_code})",
        f"error={error}",
    ]
    resets_at = body.get("resets_at")
    if isinstance(resets_at, str) and resets_at.strip():
        parts.append(f"resets_at={resets_at.strip()}")
    upgrade_url = body.get("upgrade_url")
    if isinstance(upgrade_url, str) and upgrade_url.strip():
        parts.append(f"upgrade_url={upgrade_url.strip()}")
    logger.warning("%s", "; ".join(parts))


def _find_otlp_http_exporter(exporter: Any) -> Any | None:
    """Walk exporter wrappers until an OTLP HTTP exporter with a session is found."""
    seen: set[int] = set()
    current = exporter
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "_session", None) is not None:
            return current
        current = getattr(current, "_exporter", None)
    return None


def attach_otlp_http_quota_capture(
    exporter: Any,
    *,
    on_quota: Callable[[int, str], None],
) -> None:
    """Wrap the OTLP HTTP exporter session to observe 429 response bodies."""
    leaf = _find_otlp_http_exporter(exporter)
    if leaf is None:
        return
    session = getattr(leaf, "_session", None)
    if session is None:
        return
    if getattr(session, "_parlot_quota_capture", False):
        return

    original_post = session.post

    def post(url: str, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        resp = original_post(url, *args, **kwargs)
        if getattr(resp, "status_code", None) == 429:
            try:
                on_quota(429, getattr(resp, "text", "") or "")
            except Exception:
                logger.debug("parlot: quota capture callback failed", exc_info=True)
        return resp

    session.post = post  # type: ignore[method-assign]
    session._parlot_quota_capture = True
