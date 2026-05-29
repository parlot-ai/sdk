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


def is_parlot_debug() -> bool:
    return logger.isEnabledFor(logging.DEBUG)


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
