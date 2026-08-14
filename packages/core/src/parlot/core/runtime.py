"""Cached Parlot platform bootstrap (org, R2, egress webhook URL, recording, logs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from parlot.core.logs_capture import DEFAULT_LOGS_MIN_LEVEL, normalize_log_level


@dataclass(frozen=True)
class ParlotRuntimeContext:
    endpoint: str
    api_key: str
    org_id: str
    content_bucket: str
    r2_endpoint: str
    egress_webhook_url: str
    recording_globs: tuple[str, ...] = ()
    recording_agents: tuple[tuple[str, bool], ...] = ()
    logs_globs: tuple[str, ...] = ()
    logs_agents: tuple[tuple[str, bool], ...] = ()
    logs_min_level: str = DEFAULT_LOGS_MIN_LEVEL
    # True when bootstrap JSON included a ``logs`` object (even empty).
    logs_policy_present: bool = False

    def recording_agents_map(self) -> dict[str, bool]:
        return dict(self.recording_agents)

    def logs_agents_map(self) -> dict[str, bool]:
        return dict(self.logs_agents)


_runtime: Optional[ParlotRuntimeContext] = None


def get_runtime() -> Optional[ParlotRuntimeContext]:
    return _runtime


def set_runtime(ctx: ParlotRuntimeContext) -> None:
    global _runtime
    _runtime = ctx


def clear_runtime() -> None:
    global _runtime
    _runtime = None


def _parse_recording_policy(
    payload: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, bool], ...]]:
    recording = payload.get("recording")
    if not isinstance(recording, dict):
        return (), ()

    raw_globs = recording.get("globs")
    globs: list[str] = []
    if isinstance(raw_globs, list):
        globs = [str(item).strip() for item in raw_globs if str(item).strip()]

    raw_agents = recording.get("agents")
    agents: list[tuple[str, bool]] = []
    if isinstance(raw_agents, Mapping):
        for key, value in raw_agents.items():
            agent_id = str(key).strip()
            if not agent_id:
                continue
            agents.append((agent_id, bool(value)))

    return tuple(globs), tuple(agents)


def _parse_logs_policy(
    payload: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, bool], ...], str, bool]:
    logs = payload.get("logs")
    if not isinstance(logs, dict):
        return (), (), DEFAULT_LOGS_MIN_LEVEL, False

    raw_globs = logs.get("globs")
    globs: list[str] = []
    if isinstance(raw_globs, list):
        globs = [str(item).strip() for item in raw_globs if str(item).strip()]

    raw_agents = logs.get("agents")
    agents: list[tuple[str, bool]] = []
    if isinstance(raw_agents, Mapping):
        for key, value in raw_agents.items():
            agent_id = str(key).strip()
            if not agent_id:
                continue
            agents.append((agent_id, bool(value)))

    min_level = normalize_log_level(str(logs.get("min_level") or DEFAULT_LOGS_MIN_LEVEL))
    return tuple(globs), tuple(agents), min_level, True


def runtime_from_bootstrap(
    endpoint: str, api_key: str, payload: dict[str, Any]
) -> ParlotRuntimeContext:
    globs, agents = _parse_recording_policy(payload)
    logs_globs, logs_agents, logs_min_level, logs_present = _parse_logs_policy(payload)
    return ParlotRuntimeContext(
        endpoint=endpoint.rstrip("/"),
        api_key=api_key,
        org_id=str(payload.get("org_id") or ""),
        content_bucket=str(payload.get("content_bucket") or ""),
        r2_endpoint=str(payload.get("r2_endpoint") or ""),
        egress_webhook_url=str(payload.get("egress_webhook_url") or ""),
        recording_globs=globs,
        recording_agents=agents,
        logs_globs=logs_globs,
        logs_agents=logs_agents,
        logs_min_level=logs_min_level,
        logs_policy_present=logs_present,
    )
