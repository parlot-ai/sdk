"""Cached Parlot platform bootstrap (org, R2, recording, logs, content)."""

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
    recording_globs: tuple[str, ...] = ()
    recording_agents: tuple[tuple[str, bool], ...] = ()
    logs_globs: tuple[str, ...] = ()
    logs_agents: tuple[tuple[str, bool], ...] = ()
    logs_agent_min_levels: tuple[tuple[str, str], ...] = ()
    logs_min_level: str = DEFAULT_LOGS_MIN_LEVEL
    # True when bootstrap JSON included a ``logs`` object (even empty).
    logs_policy_present: bool = False
    capture_genai_content_globs: tuple[str, ...] = ()
    capture_genai_content_agents: tuple[tuple[str, bool], ...] = ()
    # True when bootstrap JSON included a ``capture_genai_content`` object (even empty).
    capture_genai_content_policy_present: bool = False

    def recording_agents_map(self) -> dict[str, bool]:
        return dict(self.recording_agents)

    def logs_agents_map(self) -> dict[str, bool]:
        return dict(self.logs_agents)

    def logs_agent_min_levels_map(self) -> dict[str, str]:
        return dict(self.logs_agent_min_levels)

    def capture_genai_content_agents_map(self) -> dict[str, bool]:
        return dict(self.capture_genai_content_agents)


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
) -> tuple[
    tuple[str, ...],
    tuple[tuple[str, bool], ...],
    tuple[tuple[str, str], ...],
    str,
    bool,
]:
    logs = payload.get("logs")
    if not isinstance(logs, dict):
        return (), (), (), DEFAULT_LOGS_MIN_LEVEL, False

    raw_globs = logs.get("globs")
    globs: list[str] = []
    if isinstance(raw_globs, list):
        globs = [str(item).strip() for item in raw_globs if str(item).strip()]

    raw_agents = logs.get("agents")
    agents: list[tuple[str, bool]] = []
    agent_min_levels: list[tuple[str, str]] = []
    if isinstance(raw_agents, Mapping):
        for key, value in raw_agents.items():
            agent_id = str(key).strip()
            if not agent_id:
                continue
            # Bootstrap agents are objects: { "enabled": bool, "min_level"?: str }.
            if not isinstance(value, Mapping):
                continue
            if "enabled" not in value:
                continue
            enabled = bool(value.get("enabled"))
            agents.append((agent_id, enabled))
            raw_level = value.get("min_level")
            if raw_level is not None and str(raw_level).strip():
                agent_min_levels.append(
                    (agent_id, normalize_log_level(str(raw_level)))
                )

    min_level = normalize_log_level(str(logs.get("min_level") or DEFAULT_LOGS_MIN_LEVEL))
    return tuple(globs), tuple(agents), tuple(agent_min_levels), min_level, True


def _parse_capture_genai_content_policy(
    payload: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, bool], ...], bool]:
    capture_genai_content = payload.get("capture_genai_content")
    if not isinstance(capture_genai_content, dict):
        return (), (), False

    raw_globs = capture_genai_content.get("globs")
    globs: list[str] = []
    if isinstance(raw_globs, list):
        globs = [str(item).strip() for item in raw_globs if str(item).strip()]

    raw_agents = capture_genai_content.get("agents")
    agents: list[tuple[str, bool]] = []
    if isinstance(raw_agents, Mapping):
        for key, value in raw_agents.items():
            agent_id = str(key).strip()
            if not agent_id:
                continue
            agents.append((agent_id, bool(value)))

    return tuple(globs), tuple(agents), True


def runtime_from_bootstrap(
    endpoint: str, api_key: str, payload: dict[str, Any]
) -> ParlotRuntimeContext:
    globs, agents = _parse_recording_policy(payload)
    (
        logs_globs,
        logs_agents,
        logs_agent_min_levels,
        logs_min_level,
        logs_present,
    ) = _parse_logs_policy(payload)
    (
        capture_globs,
        capture_agents,
        capture_present,
    ) = _parse_capture_genai_content_policy(payload)
    return ParlotRuntimeContext(
        endpoint=endpoint.rstrip("/"),
        api_key=api_key,
        org_id=str(payload.get("org_id") or ""),
        content_bucket=str(payload.get("content_bucket") or ""),
        r2_endpoint=str(payload.get("r2_endpoint") or ""),
        recording_globs=globs,
        recording_agents=agents,
        logs_globs=logs_globs,
        logs_agents=logs_agents,
        logs_agent_min_levels=logs_agent_min_levels,
        logs_min_level=logs_min_level,
        logs_policy_present=logs_present,
        capture_genai_content_globs=capture_globs,
        capture_genai_content_agents=capture_agents,
        capture_genai_content_policy_present=capture_present,
    )
