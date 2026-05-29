"""Append-only debug log for span processor on_start/on_end (local dev)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_LOG_DIR = os.path.expanduser("~/dev/parlot.ai/logs/sdk")
_LOG_FILE = os.path.join(_LOG_DIR, "span-events.log")
_lock = threading.Lock()
_initialized = False


def _ensure_dir() -> None:
    global _initialized
    if not _initialized:
        os.makedirs(_LOG_DIR, exist_ok=True)
        _initialized = True


def _span_id_hex(span: Any) -> str:
    ctx = getattr(span, "context", None)
    if ctx is None:
        return ""
    return format(ctx.span_id, "016x")


def _trace_id_hex(span: Any) -> str:
    ctx = getattr(span, "context", None)
    if ctx is None:
        return ""
    return format(ctx.trace_id, "032x")


def _span_attrs(span: Any) -> dict[str, Any]:
    attrs = getattr(span, "attributes", None) or {}
    if hasattr(attrs, "items"):
        return {str(k): _json_safe(v) for k, v in attrs.items()}
    return {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _format_line(event: str, span: Any) -> str:
    name = getattr(span, "name", "") or ""
    parts = [
        datetime.now(timezone.utc).isoformat(),
        event,
        f"name={name!r}",
        f"trace_id={_trace_id_hex(span)}",
        f"span_id={_span_id_hex(span)}",
    ]
    attrs = _span_attrs(span)
    if attrs:
        parts.append(f"attrs={json.dumps(attrs, default=str)}")
    if event == "on_end":
        status = getattr(span, "status", None)
        if status is not None:
            code = getattr(status, "status_code", None)
            name_attr = getattr(code, "name", None)
            parts.append(f"status={name_attr if name_attr is not None else code}")
    return " ".join(parts) + "\n"


def log_span_event(event: str, span: Any) -> None:
    try:
        _ensure_dir()
        line = _format_line(event, span)
        with _lock:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
