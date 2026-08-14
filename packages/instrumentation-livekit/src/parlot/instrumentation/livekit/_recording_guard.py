"""LiveKit job context adapters for Parlot recording and logs policy."""

from __future__ import annotations

import json
from typing import Any, Optional

from parlot.core.recording import should_record as should_record_policy
from parlot.core.runtime import get_runtime
from parlot.instrumentation.livekit._agent_identity import topology_agent_name
from parlot.instrumentation.livekit._auto import (
    configured_agent_id,
    configured_record,
)


def agent_name_from_ctx(ctx: Any) -> str:
    """Return the LiveKit worker ``agent_name`` for identity / topology.

    Does **not** fall back to ``job.dispatch_id`` (``AD_…``). Those are
    per-job dispatch identifiers and must not become topology agent names.
    Unnamed workers return ``\"\"``; use ``configure(agent_id=…)`` and/or
    ``lk.agent_label`` for graph identity, and recording policy via
    ``configure(record=…)`` or Settings → Recording.
    """
    job = getattr(ctx, "job", None)
    agent_name = getattr(job, "agent_name", None) if job is not None else None
    return topology_agent_name(agent_name)


def recording_agent_id_from_ctx(ctx: Any) -> str:
    """Agent id used for recording policy (matches ``session.agent_id``)."""
    configured = configured_agent_id()
    if configured:
        return configured
    return agent_name_from_ctx(ctx)


def _job_metadata_dict(ctx: Any) -> Optional[dict[str, Any]]:
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
    return metadata


def metadata_record_flag(ctx: Any) -> Optional[bool]:
    metadata = _job_metadata_dict(ctx)
    if metadata is None or "record" not in metadata:
        return None
    return bool(metadata.get("record"))


def metadata_capture_logs_flag(ctx: Any) -> Optional[bool]:
    metadata = _job_metadata_dict(ctx)
    if metadata is None or "capture_logs" not in metadata:
        return None
    return bool(metadata.get("capture_logs"))


def should_record(ctx: Any) -> bool:
    """Return True when Room Composite egress should start for this LiveKit job."""
    runtime = get_runtime()
    return should_record_policy(
        recording_agent_id_from_ctx(ctx),
        metadata_record=metadata_record_flag(ctx),
        configure_record=configured_record(),
        bootstrap_globs=list(runtime.recording_globs) if runtime else None,
        bootstrap_agents=runtime.recording_agents_map() if runtime else None,
    )


def current_job_capture_logs_metadata() -> Optional[bool]:
    """Best-effort read of job metadata ``capture_logs`` for the active job."""
    try:
        from livekit.agents.job import get_job_context

        ctx = get_job_context()
        if ctx is None:
            return None
        return metadata_capture_logs_flag(ctx)
    except Exception:
        return None


def livekit_session_log_fields() -> Optional[dict[str, Any]]:
    """Resolve Parlot session fields for log capture (job-bootstrap aware)."""
    from ._session import get_job_bootstrap

    bootstrap = get_job_bootstrap()
    if bootstrap is None:
        return None
    state = bootstrap.state
    sid = str(getattr(state, "parlot_session_id", "") or bootstrap.session_id or "")
    if not sid:
        return None
    turn_index = int(getattr(state, "turn_count", 0) or 0)
    open_agent = getattr(state, "open_agent_turn_index", None)
    if open_agent is not None:
        try:
            turn_index = int(open_agent)
        except (TypeError, ValueError):
            pass
    return {
        "session_id": sid,
        "conversation_id": str(getattr(state, "conversation_id", "") or sid),
        "turn_index": turn_index,
    }
