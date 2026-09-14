"""Canonical agent identity helpers for LiveKit instrumentation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from parlot.core.attrs import (
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID,
    ATTR_SESSION_AGENT_ID,
)
from parlot.instrumentation.livekit._auto import (
    configured_agent_id,
    configured_agent_version,
    explicit_agent_id,
)

if TYPE_CHECKING:
    from ._session_state import _LiveKitSessionState

LIVEKIT_FRAMEWORK = "livekit"

# LiveKit Agent Dispatch IDs (protocol guid.AgentDispatchPrefix).
_LIVEKIT_DISPATCH_ID_RE = re.compile(r"^AD_[A-Za-z0-9]+$")


def is_livekit_dispatch_id(name: str | None) -> bool:
    """Return True when *name* is a LiveKit per-job dispatch id (``AD_…``)."""
    return bool(_LIVEKIT_DISPATCH_ID_RE.match(str(name or "").strip()))


def topology_agent_name(name: str | None) -> str:
    """Return *name* when usable as a topology agent id; else empty.

    LiveKit dispatch ids are temporary per-job identifiers and must not appear
    as ``gen_ai.agent.name`` / graph nodes.
    """
    cleaned = str(name or "").strip()
    if not cleaned or is_livekit_dispatch_id(cleaned):
        return ""
    return cleaned


def resolve_canonical_agent_id(state: "_LiveKitSessionState") -> str:
    """Resolve deployment identity for session + topology seeding.

    Precedence: explicit ``parlotize(agent_id=)`` → worker ``agent_name`` →
    runtime ``agent_label`` → ``configured_agent_id()``.
    """
    explicit = explicit_agent_id()
    if explicit:
        return explicit
    worker = topology_agent_name(state.worker_agent_name)
    if worker:
        return worker
    label = topology_agent_name(getattr(state, "agent_label", None) or "")
    if label:
        return label
    return configured_agent_id()


def ensure_agent_chain_seeded(state: "_LiveKitSessionState") -> None:
    canonical = resolve_canonical_agent_id(state)
    if not canonical:
        return
    if not state.agent_chain:
        state.agent_chain.append(canonical)
    elif state.agent_chain[0] != canonical:
        state.agent_chain.insert(0, canonical)


def append_agent_chain_step(state: "_LiveKitSessionState", agent: str) -> None:
    agent = topology_agent_name(agent)
    if not agent:
        return
    ensure_agent_chain_seeded(state)
    if not state.agent_chain or state.agent_chain[-1] != agent:
        state.agent_chain.append(agent)


def stamp_session_agent_identity(session_span: Any, state: "_LiveKitSessionState") -> None:
    if session_span is None or not hasattr(session_span, "set_attribute"):
        return
    agent_id = resolve_canonical_agent_id(state)
    if agent_id:
        session_span.set_attribute(ATTR_SESSION_AGENT_ID, agent_id)
    session_span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK, LIVEKIT_FRAMEWORK)
    if state.session_id:
        session_span.set_attribute(ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID, state.session_id)
    version = configured_agent_version()
    if version:
        session_span.set_attribute(ATTR_GEN_AI_AGENT_VERSION, version)
