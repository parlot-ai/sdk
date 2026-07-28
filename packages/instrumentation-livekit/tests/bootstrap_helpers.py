"""Test helpers for event-primary session bootstrap."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from parlot.instrumentation.livekit._events import LiveKitEventBridge
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import get_job_bootstrap


def make_mock_job_context(
    job_id: str = "job-test",
    *,
    room_name: str = "",
    room_sid: str = "",
    worker_agent_name: str = "",
    connected: bool = False,
) -> SimpleNamespace:
    job_room = SimpleNamespace(name=room_name, sid=room_sid) if (room_name or room_sid) else None
    job = SimpleNamespace(id=job_id, room=job_room)
    return SimpleNamespace(
        job=job,
        room=None,
        _connected=connected,
        agent_name=worker_agent_name,
    )


def bootstrap_via_agent_state(
    proc: LiveKitGenAIProcessor,
    job_id: str = "job-test",
    *,
    ctx: Any | None = None,
    worker_agent_name: str = "",
) -> tuple[Any, Any]:
    """Bootstrap session via initializing→listening without job_entrypoint span."""
    if proc._tracer is None:
        raise RuntimeError("processor tracer not set — call proc.set_tracer first")

    mock_ctx = ctx or make_mock_job_context(job_id, worker_agent_name=worker_agent_name)
    session = SimpleNamespace(
        _parlot_job_ctx=mock_ctx,
        _parlot_shutdown_reset=False,
        _parlot_bootstrapped=False,
        room=None,
        on=lambda *_a, **_k: (lambda fn: fn),
    )
    tracer = proc._tracer
    assert tracer is not None
    bridge = LiveKitEventBridge(proc, tracer)
    bridge._session = session
    bridge._on_agent_state_changed(
        SimpleNamespace(old_state="initializing", new_state="listening")
    )
    bootstrap = get_job_bootstrap()
    assert bootstrap is not None, "bootstrap_via_agent_state failed to mint session"
    return session, bootstrap


def fire_agent_state_changed(
    bridge: LiveKitEventBridge,
    old_state: str,
    new_state: str,
) -> None:
    bridge._on_agent_state_changed(
        SimpleNamespace(old_state=old_state, new_state=new_state)
    )
