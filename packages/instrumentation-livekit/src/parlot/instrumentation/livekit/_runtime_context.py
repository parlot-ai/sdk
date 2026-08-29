"""Apply telemetry bootstrap payload onto a ``ParlotContext``."""

from __future__ import annotations

from typing import Any

from parlot.core.context import ParlotContext
from parlot.core.runtime import runtime_from_bootstrap


def apply_bootstrap_payload(
    context: ParlotContext,
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
) -> None:
    """Cache platform bootstrap on ``context.runtime``."""
    context.runtime = runtime_from_bootstrap(endpoint, api_key, payload)
