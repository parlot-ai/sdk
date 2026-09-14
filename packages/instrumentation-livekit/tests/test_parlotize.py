"""Tests for parlotize() provider setup and AgentSession patch."""

from __future__ import annotations

import sys
import types

import pytest


def _install_livekit_stub():
    """Install a minimal livekit.agents stub into sys.modules."""
    if "livekit" in sys.modules:
        return

    class _AgentSession:
        _parlot_patched = False
        _parlot_emit_metrics_patched = False

        def __init__(self, *a, **kw):
            pass

        def on(self, event_name):
            def decorator(fn):
                return fn

            return decorator

        def emit(self, *a, **kw):
            pass

    class _Telemetry:
        _provider = None

        @staticmethod
        def set_tracer_provider(p):
            _Telemetry._provider = p

    livekit_agents_ns = types.SimpleNamespace(
        AgentSession=_AgentSession,
        telemetry=_Telemetry,
    )
    livekit_ns = types.SimpleNamespace(agents=livekit_agents_ns)

    sys.modules["livekit"] = livekit_ns  # type: ignore[assignment]
    sys.modules["livekit.agents"] = livekit_agents_ns  # type: ignore[assignment]
    sys.modules["livekit.agents.telemetry"] = _Telemetry  # type: ignore[assignment]


def _reset_parlotize():
    """Reset the _configured flag so parlotize() runs fresh each test."""
    import parlot.instrumentation.livekit._auto as _auto

    _auto._configured = False
    _auto._parlot_context = None
    _auto._configured_agent_id = None
    _auto._configured_agent_version = ""
    _auto._configured_record = None

    import livekit.agents as lk

    if hasattr(lk.AgentSession, "_parlot_patched"):
        lk.AgentSession._parlot_patched = False
    if hasattr(lk.AgentSession, "_parlot_emit_metrics_patched"):
        lk.AgentSession._parlot_emit_metrics_patched = False


class TestConfigureProviderSetup:
    def setup_method(self):
        _install_livekit_stub()
        _reset_parlotize()

    def test_raises_without_endpoint(self):
        from parlot.instrumentation.livekit import parlotize

        with pytest.raises(ValueError, match="PARLOT_ENDPOINT"):
            parlotize("test-agent")

    def test_raises_without_agent_id(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize

        with pytest.raises(TypeError):
            parlotize()  # type: ignore[call-arg]

    def test_raises_on_blank_agent_id(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize

        with pytest.raises(ValueError, match="agent_id"):
            parlotize("   ")

    def test_env_var_endpoint(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize

        parlotize("test-agent")

    def test_idempotent_on_double_call(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize

        parlotize("test-agent")
        parlotize("test-agent")

    def test_agent_id_required(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("custom-deployment")
        assert _auto.configured_agent_id() == "custom-deployment"
        assert _auto.explicit_agent_id() == "custom-deployment"

    def test_version_override(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("test-agent", version="2.0.0")
        assert _auto.configured_agent_version() == "2.0.0"

    def test_version_defaults_to_unknown_when_omitted(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.delenv("PARLOT_AGENT_VERSION", raising=False)
        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("test-agent")
        assert _auto.configured_agent_version() == "unknown"


class TestAgentSessionPatch:
    def setup_method(self):
        _install_livekit_stub()
        _reset_parlotize()

    def test_agent_session_marked_patched(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import parlotize

        parlotize("test-agent")

        import livekit.agents as lk

        assert lk.AgentSession._parlot_patched is True


class TestDevWatchParentSkip:
    def setup_method(self):
        _install_livekit_stub()
        _reset_parlotize()

    def test_skips_parlotize_in_dev_watch_parent(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        # ``lk agent dev`` → ``python -m livekit.agents start --dev``
        monkeypatch.setattr(sys, "argv", ["-m", "livekit.agents", "start", "--dev"])

        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("test-agent")

        assert _auto._configured is False

        import livekit.agents as lk

        assert lk.AgentSession._parlot_patched is False

    def test_skips_parlotize_in_legacy_dev_subcommand(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(sys, "argv", ["agent.py", "dev"])

        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("test-agent")

        assert _auto._configured is False

    def test_parlotizes_in_dev_worker_child(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(sys, "argv", ["-m", "livekit.agents", "start", "--dev"])

        class _SpawnProcess:
            name = "SpawnProcess-1"

        monkeypatch.setattr(
            "parlot.instrumentation.livekit._auto.multiprocessing.current_process",
            lambda: _SpawnProcess(),
        )

        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("test-agent")

        assert _auto._configured is True

    def test_parlotizes_in_dev_no_reload(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(sys, "argv", ["agent.py", "dev", "--no-reload"])

        from parlot.instrumentation.livekit import parlotize
        import parlot.instrumentation.livekit._auto as _auto

        parlotize("test-agent")

        assert _auto._configured is True
