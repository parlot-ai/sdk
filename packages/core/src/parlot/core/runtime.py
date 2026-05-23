"""Cached Parlot platform bootstrap (org, R2, egress webhook URL)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ParlotRuntimeContext:
    endpoint: str
    api_key: str
    org_id: str
    content_bucket: str
    r2_endpoint: str
    egress_webhook_url: str


_runtime: Optional[ParlotRuntimeContext] = None


def get_runtime() -> Optional[ParlotRuntimeContext]:
    return _runtime


def set_runtime(ctx: ParlotRuntimeContext) -> None:
    global _runtime
    _runtime = ctx


def clear_runtime() -> None:
    global _runtime
    _runtime = None


def runtime_from_bootstrap(
    endpoint: str, api_key: str, payload: dict[str, Any]
) -> ParlotRuntimeContext:
    return ParlotRuntimeContext(
        endpoint=endpoint.rstrip("/"),
        api_key=api_key,
        org_id=str(payload.get("org_id") or ""),
        content_bucket=str(payload.get("content_bucket") or ""),
        r2_endpoint=str(payload.get("r2_endpoint") or ""),
        egress_webhook_url=str(payload.get("egress_webhook_url") or ""),
    )
