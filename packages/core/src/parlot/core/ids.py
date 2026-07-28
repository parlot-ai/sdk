"""Parlot identifier helpers (hyphenless UUID v7 for session_id)."""

from __future__ import annotations

import os
import time
import uuid


def new_session_id() -> str:
    """32-char lowercase hex session_id (UUID v7 when available)."""
    try:
        return uuid.uuid7().hex  # type: ignore[attr-defined]
    except AttributeError:
        return _uuid7_hex_fallback()


def _uuid7_hex_fallback() -> str:
    """RFC 9562 UUID v7 without stdlib support (Python < 3.14)."""
    unix_ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big")
    uuid_int = (unix_ms & 0xFFFFFFFFFFFF) << 80
    uuid_int |= 0x7000 << 64  # version 7
    uuid_int |= rand_a << 64
    uuid_int |= 0x8000000000000000  # variant
    uuid_int |= rand_b & 0x3FFFFFFFFFFFFFFF
    return f"{uuid_int:032x}"
