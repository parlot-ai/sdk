"""Process-wide latch: drop Parlot ingest when free-plan turn quota is exhausted.

Server remains source of truth (OTLP accept still returns 429). This latch lets
the SDK stop exporting new session telemetry and skip recording without raising
into the host voice path.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Mapping, Optional

logger = logging.getLogger("parlot.core.ingest_gate")

_lock = threading.Lock()
_ingest_disabled = False
_logged = False
_disable_reason = ""
_resets_at: Optional[str] = None
_upgrade_url: Optional[str] = None


def reset_parlot_ingest_gate_for_tests() -> None:
    """Clear the process-wide ingest gate (tests only)."""
    global _ingest_disabled, _logged, _disable_reason, _resets_at, _upgrade_url
    with _lock:
        _ingest_disabled = False
        _logged = False
        _disable_reason = ""
        _resets_at = None
        _upgrade_url = None


def is_parlot_ingest_disabled() -> bool:
    with _lock:
        return _ingest_disabled


def parlot_ingest_disable_reason() -> str:
    with _lock:
        return _disable_reason or "quota_exceeded"


def _log_once_locked(
    *,
    source: str,
    error: str,
    resets_at: Optional[str],
    upgrade_url: Optional[str],
) -> None:
    global _logged
    if _logged:
        return
    _logged = True
    parts = [
        f"Parlot ingest disabled ({source})",
        f"error={error}",
    ]
    if resets_at:
        parts.append(f"resets_at={resets_at}")
    if upgrade_url:
        parts.append(f"upgrade_url={upgrade_url}")
    logger.warning("%s", "; ".join(parts))


def disable_parlot_ingest(
    *,
    source: str,
    error: str = "quota_exceeded",
    resets_at: Optional[str] = None,
    upgrade_url: Optional[str] = None,
) -> None:
    """Latch ingest off for this process. Safe to call repeatedly."""
    global _ingest_disabled, _disable_reason, _resets_at, _upgrade_url
    with _lock:
        _ingest_disabled = True
        _disable_reason = error or "quota_exceeded"
        if resets_at:
            _resets_at = resets_at
        if upgrade_url:
            _upgrade_url = upgrade_url
        _log_once_locked(
            source=source,
            error=_disable_reason,
            resets_at=_resets_at,
            upgrade_url=_upgrade_url,
        )


def _parse_json_object(body_text: str) -> dict[str, Any]:
    try:
        data = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def disable_parlot_ingest_from_quota_body(
    *,
    source: str,
    status_code: int,
    body_text: str,
) -> None:
    """Latch from an OTLP/upload-grant HTTP 429 JSON body."""
    body = _parse_json_object(body_text)
    error = body.get("error") or body.get("code") or "quota_exceeded"
    if not isinstance(error, str) or not error.strip():
        error = "quota_exceeded"
    resets_at = body.get("resets_at")
    upgrade_url = body.get("upgrade_url")
    disable_parlot_ingest(
        source=f"{source}:http_{status_code}",
        error=error.strip(),
        resets_at=resets_at.strip() if isinstance(resets_at, str) else None,
        upgrade_url=upgrade_url.strip() if isinstance(upgrade_url, str) else None,
    )


def apply_bootstrap_ingest_policy(payload: Mapping[str, Any]) -> bool:
    """Apply bootstrap ``ingest`` object. Returns True when ingest remains allowed."""
    ingest = payload.get("ingest")
    if not isinstance(ingest, Mapping):
        # Older collectors omit the field — keep exporting; accept still enforces.
        return not is_parlot_ingest_disabled()
    allowed = ingest.get("allowed")
    if allowed is True or allowed is None:
        return not is_parlot_ingest_disabled()
    if allowed is False:
        error = ingest.get("error") or "quota_exceeded"
        if not isinstance(error, str) or not error.strip():
            error = "quota_exceeded"
        resets_at = ingest.get("resets_at")
        upgrade_url = ingest.get("upgrade_url")
        disable_parlot_ingest(
            source="bootstrap",
            error=error.strip(),
            resets_at=resets_at.strip() if isinstance(resets_at, str) else None,
            upgrade_url=upgrade_url.strip() if isinstance(upgrade_url, str) else None,
        )
        return False
    return not is_parlot_ingest_disabled()
