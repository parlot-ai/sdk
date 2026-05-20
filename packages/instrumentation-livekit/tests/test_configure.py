"""Tests for configure() auto-wiring: _JobProc entrypoint wrapping and provider setup."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Stub minimal livekit.agents so tests run without the actual SDK installed
# ---------------------------------------------------------------------------

def _install_livekit_stub():
    """Install a minimal livekit.agents stub into sys.modules.

    Uses types.SimpleNamespace so attribute access is transparent with no
    MagicMock auto-generation side-effects.
    """
    if "livekit" in sys.modules:
        return

    class _Room:
        name = "test-room"
        sid  = "RM_test_sid"

    class _Job:
        id = "job-stub"

    class _Ctx:
        job  = _Job()
        room = _Room()

    class _AgentSession:
        _parlot_patched = False

        def __init__(self, *a, **kw):
            pass

        def on(self, event_name):
            def decorator(fn):
                return fn
            return decorator

    class _WorkerOptions:
        _parlot_patched = False

        def __init__(self, entrypoint_fnc=None, **kwargs):
            self.entrypoint_fnc = entrypoint_fnc

    class _JobProc:
        _parlot_patched = False

        def __init__(self, job_entrypoint_fnc=None, **kwargs):
            self._job_entrypoint_fnc = job_entrypoint_fnc

    _JobProc._parlot_original_init = _JobProc.__init__  # type: ignore[attr-defined]

    class _Telemetry:
        _provider = None

        @staticmethod
        def set_tracer_provider(p):
            _Telemetry._provider = p

    # Use SimpleNamespace so attribute lookup is a plain dict lookup —
    # no MagicMock child-mock auto-generation that could shadow our classes.
    ipc_ns = types.SimpleNamespace(job_proc_lazy_main=types.SimpleNamespace(_JobProc=_JobProc))
    livekit_agents_ns = types.SimpleNamespace(
        WorkerOptions=_WorkerOptions,
        AgentSession=_AgentSession,
        telemetry=_Telemetry,
        ipc=ipc_ns,
    )
    livekit_ns = types.SimpleNamespace(agents=livekit_agents_ns)

    sys.modules["livekit"] = livekit_ns  # type: ignore[assignment]
    sys.modules["livekit.agents"] = livekit_agents_ns  # type: ignore[assignment]
    sys.modules["livekit.agents.telemetry"] = _Telemetry  # type: ignore[assignment]
    sys.modules["livekit.agents.ipc"] = ipc_ns  # type: ignore[assignment]
    sys.modules["livekit.agents.ipc.job_proc_lazy_main"] = ipc_ns.job_proc_lazy_main  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_configure():
    """Reset the _configured flag so configure() runs fresh each test."""
    import parlot.instrumentation.livekit._auto as _auto
    _auto._configured = False

    import livekit.agents as lk
    if hasattr(lk.WorkerOptions, "_parlot_patched"):
        lk.WorkerOptions._parlot_patched = False
    if hasattr(lk.AgentSession, "_parlot_patched"):
        lk.AgentSession._parlot_patched = False

    try:
        from livekit.agents.ipc.job_proc_lazy_main import _JobProc

        if hasattr(_JobProc, "_parlot_original_init"):
            _JobProc.__init__ = _JobProc._parlot_original_init  # type: ignore[method-assign]
        _JobProc._parlot_patched = False
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

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
        configure()  # should not raise

    def test_idempotent_on_double_call(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure
        configure()
        configure()  # second call should be a no-op, not raise


class TestJobProcEntrypointPatch:
    def setup_method(self):
        _install_livekit_stub()
        _reset_configure()

    def test_worker_options_entrypoint_not_wrapped(self, monkeypatch):
        """Wrapping happens in _JobProc (pickle-safe), not WorkerOptions."""
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure
        configure()

        import livekit.agents as lk

        async def _my_entrypoint(ctx):
            pass

        opts = lk.WorkerOptions(entrypoint_fnc=_my_entrypoint)
        assert opts.entrypoint_fnc is _my_entrypoint

    def test_job_proc_wraps_entrypoint(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure
        configure()

        from livekit.agents.ipc.job_proc_lazy_main import _JobProc

        async def _my_entrypoint(ctx):
            pass

        proc = _JobProc(job_entrypoint_fnc=_my_entrypoint)
        assert proc._job_entrypoint_fnc is not _my_entrypoint

    @pytest.mark.asyncio
    async def test_wrapped_entrypoint_registers_context(self, monkeypatch):
        monkeypatch.setenv("PARLOT_ENDPOINT", "http://localhost:4318")
        from parlot.instrumentation.livekit import configure
        configure()

        from livekit.agents.ipc.job_proc_lazy_main import _JobProc
        from parlot.instrumentation.livekit._platform_refs import lookup_room_context

        ctx_stub = types.SimpleNamespace(
            job=types.SimpleNamespace(id="job-wrapped"),
            room=types.SimpleNamespace(name="room-wrapped", sid="RM_wrapped"),
        )

        executed = []

        async def _entrypoint(ctx):
            executed.append(ctx)

        proc = _JobProc(job_entrypoint_fnc=_entrypoint)
        await proc._job_entrypoint_fnc(ctx_stub)

        assert executed == [ctx_stub]
        assert lookup_room_context("job-wrapped") == ("room-wrapped", "RM_wrapped")


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
