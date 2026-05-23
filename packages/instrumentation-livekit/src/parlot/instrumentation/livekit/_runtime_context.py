"""LiveKit-specific bootstrap fields layered on Parlot platform runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from parlot.core.runtime import (
    ParlotRuntimeContext,
    runtime_from_bootstrap,
    set_runtime,
)


@dataclass(frozen=True)
class LiveKitRuntimeContext:
    platform: ParlotRuntimeContext
    webhook_signing_key: str


_livekit_runtime: Optional[LiveKitRuntimeContext] = None


def get_livekit_runtime() -> Optional[LiveKitRuntimeContext]:
    return _livekit_runtime


def set_livekit_runtime(ctx: LiveKitRuntimeContext) -> None:
    global _livekit_runtime
    _livekit_runtime = ctx
    set_runtime(ctx.platform)


def clear_livekit_runtime() -> None:
    global _livekit_runtime
    _livekit_runtime = None


def livekit_runtime_from_bootstrap(
    endpoint: str, api_key: str, payload: dict[str, Any]
) -> Optional[LiveKitRuntimeContext]:
    """Build LiveKit runtime when bootstrap includes a webhook signing key."""
    signing_key = str(payload.get("livekit_webhook_signing_key") or "").strip()
    if not signing_key:
        return None
    return LiveKitRuntimeContext(
        platform=runtime_from_bootstrap(endpoint, api_key, payload),
        webhook_signing_key=signing_key,
    )


def apply_bootstrap_payload(endpoint: str, api_key: str, payload: dict[str, Any]) -> bool:
    """Cache platform bootstrap; LiveKit recording fields only when signing key present.

    Returns True when LiveKit egress webhook config is available.
    """
    platform = runtime_from_bootstrap(endpoint, api_key, payload)
    set_runtime(platform)

    lk = livekit_runtime_from_bootstrap(endpoint, api_key, payload)
    if lk is not None:
        global _livekit_runtime
        _livekit_runtime = lk
        return True

    clear_livekit_runtime()
    return False
