"""Tests for agent deployment version resolution."""

from __future__ import annotations

import sys
import types

from parlot.instrumentation.livekit._agent_version import resolve_agent_version


def test_resolve_prefers_explicit_kwarg(monkeypatch):
    monkeypatch.setenv("PARLOT_AGENT_VERSION", "env-ver")
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    sys.modules["__main__"].__version__ = "main-ver"
    assert resolve_agent_version("kwarg-ver") == "kwarg-ver"


def test_resolve_prefers_main_version_over_env(monkeypatch):
    monkeypatch.delenv("PARLOT_AGENT_VERSION", raising=False)
    main = types.ModuleType("__main__")
    main.__version__ = "1.2.3"
    monkeypatch.setitem(sys.modules, "__main__", main)
    monkeypatch.setenv("PARLOT_AGENT_VERSION", "env-override")
    assert resolve_agent_version(None) == "1.2.3"


def test_resolve_uses_env_when_main_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    monkeypatch.setenv("PARLOT_AGENT_VERSION", "env-only")
    assert resolve_agent_version(None) == "env-only"


def test_resolve_supports_version_constant_on_main(monkeypatch):
    monkeypatch.delenv("PARLOT_AGENT_VERSION", raising=False)
    main = types.ModuleType("__main__")
    main.VERSION = "legacy-ver"
    monkeypatch.setitem(sys.modules, "__main__", main)
    assert resolve_agent_version(None) == "legacy-ver"


def test_resolve_does_not_use_dependency_version(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PARLOT_AGENT_VERSION", raising=False)
    dep = types.ModuleType("livekit.agents")
    dep.__version__ = "9.9.9"
    monkeypatch.setitem(sys.modules, "livekit.agents", dep)
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    assert resolve_agent_version(None) == ""


def test_resolve_ignores_ci_env_vars(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    monkeypatch.delenv("PARLOT_AGENT_VERSION", raising=False)
    monkeypatch.setenv("GITHUB_SHA", "abc123def456")
    monkeypatch.setenv("GIT_COMMIT", "also-ignored")
    assert resolve_agent_version(None) == ""


def test_resolve_truncates_long_values():
    assert len(resolve_agent_version("x" * 100)) == 64


def test_resolve_uses_caller_module_version(monkeypatch):
    """When __main__ has no version (LiveKit IPC), use the calling module."""
    monkeypatch.delenv("PARLOT_AGENT_VERSION", raising=False)
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))

    # Simulate agent.py defining __version__ then calling resolve via a helper
    # that lives in a non-parlot module name on the stack.
    agent_mod = types.ModuleType("drive_thru_agent")
    agent_mod.__version__ = "0.1.0"
    monkeypatch.setitem(sys.modules, "drive_thru_agent", agent_mod)

    def _agent_entrypoint():
        return resolve_agent_version(None)

    agent_mod.resolve = _agent_entrypoint  # type: ignore[attr-defined]
    # Bind globals so stack walk sees drive_thru_agent.__version__
    _agent_entrypoint.__globals__.clear()  # type: ignore[attr-defined]
    # Can't clear real function globals; instead exec in module dict:
    ns = agent_mod.__dict__
    exec(
        "def _call():\n"
        "    from parlot.instrumentation.livekit._agent_version import resolve_agent_version\n"
        "    return resolve_agent_version(None)\n",
        ns,
    )
    assert ns["_call"]() == "0.1.0"
