"""Fail-open helpers when Parlot OTLP ingest returns HTTP 429."""

from __future__ import annotations

import logging
from typing import Any, Callable

from parlot.core.ingest_gate import (
    disable_parlot_ingest_from_quota_body,
    reset_parlot_ingest_gate_for_tests,
)

logger = logging.getLogger("parlot.core.otlp_quota")


def reset_parlot_quota_log_for_tests() -> None:
    """Clear the process-wide quota warning latch (tests only)."""
    reset_parlot_ingest_gate_for_tests()


def log_parlot_ingest_quota_once(
    *,
    channel: str,
    status_code: int,
    body_text: str,
) -> None:
    """Latch ingest off and emit at most one quota warning per process."""
    disable_parlot_ingest_from_quota_body(
        source=f"otlp_{channel}",
        status_code=status_code,
        body_text=body_text,
    )


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
