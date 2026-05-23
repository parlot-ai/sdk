"""LiveKit job context adapters for Parlot recording policy."""

from __future__ import annotations

import json
from typing import Any, Optional

from parlot.core.recording import should_record as should_record_policy


def agent_name_from_ctx(ctx: Any) -> str:
    job = getattr(ctx, "job", None)
    agent_name = getattr(job, "agent_name", None) if job is not None else None
    if agent_name:
        return str(agent_name)
    dispatch = getattr(job, "dispatch_id", None) if job is not None else None
    if dispatch:
        return str(dispatch)
    return ""


def metadata_record_flag(ctx: Any) -> Optional[bool]:
    job = getattr(ctx, "job", None)
    if job is None:
        return None
    metadata = getattr(job, "metadata", None) or getattr(job, "metadata_json", None)
    if metadata is None:
        return None
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return None
    if not isinstance(metadata, dict):
        return None
    if "record" not in metadata:
        return None
    return bool(metadata.get("record"))


def should_record(ctx: Any) -> bool:
    """Return True when Room Composite egress should start for this LiveKit job."""
    return should_record_policy(
        agent_name_from_ctx(ctx),
        metadata_record=metadata_record_flag(ctx),
    )
