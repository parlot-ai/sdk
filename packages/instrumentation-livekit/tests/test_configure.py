"""Tests for configure() provider setup and AgentSession patch."""

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


def _reset_configure():
    """Reset the _configured flag so configure() runs fresh each test."""
    import parlot.instrumentation.livekit._auto as _auto

    _auto._configured = False

    import livekit.agents as lk

    if hasattr(lk.AgentSession, "_parlot_patched"):
        lk.AgentSession._parlot_patched = False
    if hasattr(lk.AgentSession, "_parlot_emit_metrics_patched"):
        lk.AgentSession._parlot_emit_metrics_patched = False


class TestConfigureProviderSetup:
    def setup_method(self):
        _install_livekit_stub()
        _reset_configure()

    def test_raises_without_endpoint(self):
        from parlot.instrumentation.livekit import configure

        with pytest.raises(ValueError, match="PARLOT_ENDPOINT"):
            configure()

    def test_env_var_endpoint(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure

        configure()

    def test_idempotent_on_double_call(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure

        configure()
        configure()


class TestAgentSessionPatch:
    def setup_method(self):
        _install_livekit_stub()
        _reset_configure()

    def test_agent_session_marked_patched(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure

        configure()

        import livekit.agents as lk

        assert lk.AgentSession._parlot_patched is True


class TestDevWatchParentSkip:
    def setup_method(self):
        _install_livekit_stub()
        _reset_configure()

    def test_skips_configure_in_dev_watch_parent(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(sys, "argv", ["agent.py", "dev"])
        monkeypatch.setattr(
            "parlot.instrumentation.livekit._auto.multiprocessing.parent_process",
            lambda: None,
        )

        from parlot.instrumentation.livekit import configure
        import parlot.instrumentation.livekit._auto as _auto

        configure()

        assert _auto._configured is False

        import livekit.agents as lk

        assert lk.AgentSession._parlot_patched is False

    def test_configures_in_dev_worker_child(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(sys, "argv", ["agent.py", "dev"])
        monkeypatch.setattr(
            "parlot.instrumentation.livekit._auto.multiprocessing.parent_process",
            lambda: object(),
        )

        from parlot.instrumentation.livekit import configure
        import parlot.instrumentation.livekit._auto as _auto

        configure()

        assert _auto._configured is True

    def test_configures_in_dev_no_reload(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(sys, "argv", ["agent.py", "dev", "--no-reload"])
        monkeypatch.setattr(
            "parlot.instrumentation.livekit._auto.multiprocessing.parent_process",
            lambda: None,
        )

        from parlot.instrumentation.livekit import configure
        import parlot.instrumentation.livekit._auto as _auto

        configure()

        assert _auto._configured is True
