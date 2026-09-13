"""Tests for agent deployment version resolution."""

from __future__ import annotations

from parlot.instrumentation.livekit._agent_version import resolve_agent_version


def test_resolve_prefers_explicit_kwarg():
    assert resolve_agent_version("kwarg-ver") == "kwarg-ver"


def test_resolve_defaults_to_unknown_when_omitted():
    assert resolve_agent_version(None) == "unknown"


def test_resolve_defaults_to_unknown_when_blank():
    assert resolve_agent_version("") == "unknown"
    assert resolve_agent_version("   ") == "unknown"


def test_resolve_truncates_long_values():
    assert len(resolve_agent_version("x" * 100)) == 64
