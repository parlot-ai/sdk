"""Fetch and cache Parlot telemetry bootstrap into ``ParlotRuntimeContext``."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("parlot.core.bootstrap")


def fetch_telemetry_bootstrap(
    endpoint: str,
    api_key: str,
    *,
    timeout: float = 15.0,
) -> Optional[dict[str, Any]]:
    """GET ``/v1/telemetry/bootstrap`` and return the JSON payload, or None."""
    if not endpoint or not api_key:
        return None

    import httpx

    from parlot.core.runtime import runtime_from_bootstrap, set_runtime

    url = f"{endpoint.rstrip('/')}/v1/telemetry/bootstrap"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
        if resp.status_code >= 400:
            logger.error(
                "parlot: telemetry bootstrap failed status=%s",
                resp.status_code,
            )
            return None
        payload = resp.json()
        if not isinstance(payload, dict):
            logger.error("parlot: telemetry bootstrap returned non-object JSON")
            return None
        set_runtime(runtime_from_bootstrap(endpoint, api_key, payload))
        return payload
    except Exception:
        logger.exception("parlot: telemetry bootstrap request failed")
        return None
