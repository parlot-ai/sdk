"""LiveKit-specific bootstrap layering on Parlot platform runtime."""

from __future__ import annotations

from typing import Any, Optional

from parlot.core.runtime import (
    ParlotRuntimeContext,
    runtime_from_bootstrap,
    set_runtime,
)

_livekit_runtime: Optional[ParlotRuntimeContext] = None


def get_livekit_runtime() -> Optional[ParlotRuntimeContext]:
    return _livekit_runtime


def set_livekit_runtime(ctx: ParlotRuntimeContext) -> None:
    global _livekit_runtime
    _livekit_runtime = ctx
    set_runtime(ctx)


def clear_livekit_runtime() -> None:
    global _livekit_runtime
    _livekit_runtime = None


def apply_bootstrap_payload(endpoint: str, api_key: str, payload: dict[str, Any]) -> None:
    """Cache platform bootstrap for LiveKit instrumentation."""
    set_livekit_runtime(runtime_from_bootstrap(endpoint, api_key, payload))
