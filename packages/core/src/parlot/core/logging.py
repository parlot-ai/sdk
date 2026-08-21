"""Debug logging for span processor events.

Set ``PARLOT_DEBUG_LEVEL=DEBUG`` to emit span lifecycle lines. Ensure the root
logger is configured in your app entry point (``logging.basicConfig``) so
messages reach stdout.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_level = os.getenv("PARLOT_DEBUG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, _level, logging.INFO))

# Max characters per attribute value in debug logs (full values still export).
_LOG_VALUE_MAX_LEN = 32


def is_parlot_debug() -> bool:
    return logger.isEnabledFor(logging.DEBUG)


def _span_id_hex(span: Any) -> str:
    ctx = getattr(span, "context", None)
    if ctx is None:
        return ""
    span_id = getattr(ctx, "span_id", None)
    if isinstance(span_id, int):
        return format(span_id, "016x")
    try:
        return format(int(span_id), "016x")  # type: ignore[arg-type]
    except Exception:
        return str(span_id or "")


def _trace_id_hex(span: Any) -> str:
    ctx = getattr(span, "context", None)
    if ctx is None:
        return ""
    trace_id = getattr(ctx, "trace_id", None)
    if isinstance(trace_id, int):
        return format(trace_id, "032x")
    try:
        return format(int(trace_id), "032x")  # type: ignore[arg-type]
    except Exception:
        return str(trace_id or "")


def _trim_for_log(value: str, *, max_len: int = _LOG_VALUE_MAX_LEN) -> str:
    if len(value) <= max_len:
        return value
    omitted = len(value) - max_len
    return f"{value[:max_len]}…(+{omitted})"


def _json_safe(value: Any) -> Any:
    if isinstance(value, str):
        return _trim_for_log(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return _trim_for_log(value.hex())
    return _trim_for_log(str(value))


def format_attrs_for_log(attrs: Any) -> str:
    """JSON-format span attributes for debug logs with long values truncated."""
    if not attrs:
        return "{}"
    if hasattr(attrs, "items"):
        safe = {str(k): _json_safe(v) for k, v in attrs.items()}
    else:
        safe = {}
    return json.dumps(safe, default=str)


def _span_attrs(span: Any) -> dict[str, Any]:
    attrs = getattr(span, "attributes", None) or {}
    if hasattr(attrs, "items"):
        return {str(k): _json_safe(v) for k, v in attrs.items()}
    return {}


def _format_message(event: str, span: Any) -> str:
    name = getattr(span, "name", "") or ""
    parts = [
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
    return " ".join(parts)


def log_span_event(event: str, span: Any) -> None:
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("%s", _format_message(event, span))
