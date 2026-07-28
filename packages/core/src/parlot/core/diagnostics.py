"""SDK self-diagnostics buffer.

Default ON. Opt out with ``PARLOT_DIAGNOSTICS=off`` (also ``0`` / ``false`` / ``no``).

Hard requirements:
- Never raises into the customer agent
- Never carries conversation content
- Drop under sustained failure (no queue-and-retry storm)
- Circuit breaker after consecutive flush failures
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_OPT_OUT = frozenset({"off", "0", "false", "no"})

# Bounded ring buffer — drop oldest under pressure.
_MAX_BUFFER = 64
# After this many consecutive flush failures, stop attempting until cooldown.
_CIRCUIT_FAILURES = 3
_CIRCUIT_COOLDOWN_S = 60.0
# Minimum interval between flushes.
_FLUSH_INTERVAL_S = 15.0


@dataclass
class DiagnosticEvent:
    kind: str
    message: str
    attributes: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind[:128],
            "message": self.message[:1024],
            "attributes": self.attributes,
            "ts": self.ts,
        }


_lock = threading.Lock()
_buffer: deque[DiagnosticEvent] = deque(maxlen=_MAX_BUFFER)
_consecutive_failures = 0
_circuit_open_until = 0.0
_last_flush_at = 0.0
_endpoint = ""
_api_key = ""
_flush_thread: threading.Thread | None = None
_stop = threading.Event()


def diagnostics_enabled() -> bool:
    raw = os.getenv("PARLOT_DIAGNOSTICS", "on").strip().lower()
    return raw not in _OPT_OUT


def init_diagnostics(*, endpoint: str = "", api_key: str = "") -> None:
    """Allocate buffer + start background flusher when enabled."""
    global _endpoint, _api_key, _flush_thread
    if not diagnostics_enabled():
        return
    with _lock:
        _endpoint = (endpoint or os.environ.get("PARLOT_ENDPOINT", "")).rstrip("/")
        _api_key = api_key or os.environ.get("PARLOT_API_KEY", "")
        if _flush_thread is None or not _flush_thread.is_alive():
            _stop.clear()
            _flush_thread = threading.Thread(
                target=_flush_loop,
                name="parlot-diagnostics-flush",
                daemon=True,
            )
            _flush_thread.start()


def record_diagnostic(
    kind: str,
    message: str,
    *,
    exc: BaseException | None = None,
    attributes: dict[str, Any] | None = None,
) -> None:
    """Record a diagnostic event. Never raises."""
    try:
        if not diagnostics_enabled():
            return
        attrs = dict(attributes or {})
        if exc is not None:
            attrs.setdefault("exc_type", type(exc).__name__)
        event = DiagnosticEvent(
            kind=kind,
            message=message or (str(exc) if exc else ""),
            attributes=attrs,
        )
        with _lock:
            _buffer.append(event)
    except Exception:
        return


def drain_diagnostics() -> list[DiagnosticEvent]:
    with _lock:
        events = list(_buffer)
        _buffer.clear()
        return events


def snapshot_diagnostics() -> list[DiagnosticEvent]:
    with _lock:
        return list(_buffer)


def _circuit_open() -> bool:
    return time.time() < _circuit_open_until


def _flush_loop() -> None:
    while not _stop.wait(_FLUSH_INTERVAL_S):
        try:
            _try_flush()
        except Exception:
            continue


def _try_flush() -> None:
    global _consecutive_failures, _circuit_open_until, _last_flush_at

    if not diagnostics_enabled():
        return
    if _circuit_open():
        # Drop buffered events under sustained failure — do not queue forever.
        with _lock:
            _buffer.clear()
        return
    if not _endpoint or not _api_key:
        return

    now = time.time()
    if now - _last_flush_at < _FLUSH_INTERVAL_S * 0.5:
        return

    events = drain_diagnostics()
    if not events:
        return

    ok = _post_events(events)
    _last_flush_at = time.time()
    if ok:
        _consecutive_failures = 0
        return

    _consecutive_failures += 1
    # Drop — do not re-queue. Retry storm prevention.
    if _consecutive_failures >= _CIRCUIT_FAILURES:
        _circuit_open_until = time.time() + _CIRCUIT_COOLDOWN_S
        _consecutive_failures = 0


def _post_events(events: list[DiagnosticEvent]) -> bool:
    """Fire-and-forget POST. Returns False on any failure (caller drops)."""
    try:
        import httpx
    except Exception:
        return False

    url = f"{_endpoint}/v1/diagnostics"
    payload = {"events": [e.to_payload() for e in events[:50]]}
    try:
        with httpx.Client(timeout=3.0) as client:
            res = client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {_api_key}"},
            )
            return 200 <= res.status_code < 300
    except Exception:
        return False


def shutdown_diagnostics() -> None:
    _stop.set()
