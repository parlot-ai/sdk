"""Tests for canonical agent identity stamping."""

from __future__ import annotations

from dataclasses import dataclass, field

from parlot.core.attrs import (
    ATTR_GEN_AI_AGENT_VERSION,
    ATTR_SESSION_AGENT_FRAMEWORK,
    ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID,
    ATTR_SESSION_AGENT_ID,
)
from parlot.instrumentation.livekit._agent_identity import (
    append_agent_chain_step,
    ensure_agent_chain_seeded,
    is_livekit_dispatch_id,
    is_minted_fallback_agent_id,
    mint_fallback_agent_id,
    resolve_canonical_agent_id,
    stamp_session_agent_identity,
    topology_agent_name,
)


@dataclass
class _State:
    worker_agent_name: str = ""
    session_id: str = ""
    agent_label: str = ""
    agent_chain: list[str] = field(default_factory=list)


class _Span:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


def test_mint_fallback_agent_id_format():
    minted = mint_fallback_agent_id()
    assert is_minted_fallback_agent_id(minted)
    assert minted != mint_fallback_agent_id()


def test_resolve_canonical_agent_id_prefers_parlotize_override(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "configured-id",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "configured-id",
    )
    state = _State(worker_agent_name="worker-name")
    assert resolve_canonical_agent_id(state) == "configured-id"


def test_resolve_canonical_agent_id_falls_back_to_worker_name(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "agent-aaaaaa",
    )
    state = _State(worker_agent_name="hotel-receptionist")
    assert resolve_canonical_agent_id(state) == "hotel-receptionist"


def test_resolve_canonical_prefers_worker_over_mint(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "agent-bbbbbb",
    )
    state = _State(worker_agent_name="drive-thru")
    assert resolve_canonical_agent_id(state) == "drive-thru"


def test_resolve_canonical_falls_back_to_agent_label(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "agent-cccccc",
    )
    state = _State(worker_agent_name="", agent_label="DriveThruAgent")
    assert resolve_canonical_agent_id(state) == "DriveThruAgent"


def test_resolve_canonical_falls_back_to_mint(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "agent-dddddd",
    )
    state = _State(worker_agent_name="", agent_label="")
    assert resolve_canonical_agent_id(state) == "agent-dddddd"


def test_ensure_agent_chain_seeds_canonical_deployment(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "",
    )
    state = _State(worker_agent_name="hotel-receptionist")
    ensure_agent_chain_seeded(state)
    assert state.agent_chain == ["hotel-receptionist"]


def test_append_agent_chain_step_builds_routing_path(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "",
    )
    state = _State(worker_agent_name="hotel-receptionist")
    append_agent_chain_step(state, "Orchestrator")
    append_agent_chain_step(state, "cancel_task")
    assert state.agent_chain == [
        "hotel-receptionist",
        "Orchestrator",
        "cancel_task",
    ]


def test_stamp_session_agent_identity(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_version",
        lambda: "1.2.3",
    )
    span = _Span()
    state = _State(worker_agent_name="hotel-receptionist", session_id="job-123")
    stamp_session_agent_identity(span, state)
    assert span.attributes[ATTR_SESSION_AGENT_ID] == "hotel-receptionist"
    assert span.attributes[ATTR_SESSION_AGENT_FRAMEWORK] == "livekit"
    assert span.attributes[ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID] == "job-123"
    assert span.attributes[ATTR_GEN_AI_AGENT_VERSION] == "1.2.3"


def test_is_livekit_dispatch_id():
    assert is_livekit_dispatch_id("AD_GAJ5UrwGKqsZ") is True
    assert is_livekit_dispatch_id("AD_NrRASAvBPGAx") is True
    assert is_livekit_dispatch_id("hotel-receptionist") is False
    assert is_livekit_dispatch_id("greeter") is False
    assert is_livekit_dispatch_id("") is False


def test_topology_agent_name_strips_dispatch_ids():
    assert topology_agent_name("AD_fSkdjADywDrh") == ""
    assert topology_agent_name("greeter") == "greeter"


def test_resolve_canonical_ignores_dispatch_id_worker_name(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "agent-eeeeee",
    )
    state = _State(worker_agent_name="AD_GAJ5UrwGKqsZ")
    assert resolve_canonical_agent_id(state) == "agent-eeeeee"


def test_append_agent_chain_step_skips_dispatch_ids(monkeypatch):
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.explicit_agent_id",
        lambda: "restaurant-agent",
    )
    monkeypatch.setattr(
        "parlot.instrumentation.livekit._agent_identity.configured_agent_id",
        lambda: "restaurant-agent",
    )
    state = _State()
    append_agent_chain_step(state, "AD_NrRASAvBPGAx")
    append_agent_chain_step(state, "greeter")
    assert state.agent_chain == ["restaurant-agent", "greeter"]
