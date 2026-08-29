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


def diagnostics_enabled() -> bool:
    raw = os.getenv("PARLOT_DIAGNOSTICS", "on").strip().lower()
    return raw not in _OPT_OUT


class DiagnosticsCollector:
    """Per-``ParlotContext`` diagnostics buffer and background flusher."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffer: deque[DiagnosticEvent] = deque(maxlen=_MAX_BUFFER)
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._last_flush_at = 0.0
        self._endpoint = ""
        self._api_key = ""
        self._flush_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def init(self, *, endpoint: str = "", api_key: str = "") -> None:
        """Allocate buffer + start background flusher when enabled."""
        if not diagnostics_enabled():
            return
        with self._lock:
            self._endpoint = (endpoint or os.environ.get("PARLOT_ENDPOINT", "")).rstrip("/")
            self._api_key = api_key or os.environ.get("PARLOT_API_KEY", "")
            if self._flush_thread is None or not self._flush_thread.is_alive():
                self._stop.clear()
                self._flush_thread = threading.Thread(
                    target=self._flush_loop,
                    name="parlot-diagnostics-flush",
                    daemon=True,
                )
                self._flush_thread.start()

    def record(
        self,
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
            with self._lock:
                self._buffer.append(event)
        except Exception:
            return

    def drain(self) -> list[DiagnosticEvent]:
        with self._lock:
            events = list(self._buffer)
            self._buffer.clear()
            return events

    def snapshot(self) -> list[DiagnosticEvent]:
        with self._lock:
            return list(self._buffer)

    def _circuit_open(self) -> bool:
        return time.time() < self._circuit_open_until

    def _flush_loop(self) -> None:
        while not self._stop.wait(_FLUSH_INTERVAL_S):
            try:
                self._try_flush()
            except Exception:
                continue

    def _try_flush(self) -> None:
        if not diagnostics_enabled():
            return
        if self._circuit_open():
            # Drop buffered events under sustained failure — do not queue forever.
            with self._lock:
                self._buffer.clear()
            return
        if not self._endpoint or not self._api_key:
            return

        now = time.time()
        if now - self._last_flush_at < _FLUSH_INTERVAL_S * 0.5:
            return

        events = self.drain()
        if not events:
            return

        ok = self._post_events(events)
        self._last_flush_at = time.time()
        if ok:
            self._consecutive_failures = 0
            return

        self._consecutive_failures += 1
        # Drop — do not re-queue. Retry storm prevention.
        if self._consecutive_failures >= _CIRCUIT_FAILURES:
            self._circuit_open_until = time.time() + _CIRCUIT_COOLDOWN_S
            self._consecutive_failures = 0

    def _post_events(self, events: list[DiagnosticEvent]) -> bool:
        """Fire-and-forget POST. Returns False on any failure (caller drops)."""
        try:
            import httpx
        except Exception:
            return False

        url = f"{self._endpoint}/v1/diagnostics"
        payload = {"events": [e.to_payload() for e in events[:50]]}
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return 200 <= res.status_code < 300
        except Exception:
            return False

    def shutdown(self) -> None:
        self._stop.set()
