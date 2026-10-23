"""Tool-call hook + open-session log correlation helpers."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider

from parlot.core.session import clear_active_session
from parlot.instrumentation.pipecat._hooks import install_tool_call_hooks
from parlot.instrumentation.pipecat._session import (
    _sessions_by_conversation,
    any_open_session,
    close_session,
    ensure_session,
    set_identity,
    set_tracer,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_session()
    _sessions_by_conversation.clear()
    yield
    for cid in list(_sessions_by_conversation):
        close_session(cid, reason="test_teardown")
    _sessions_by_conversation.clear()
    clear_active_session()


def test_install_tool_call_hooks_wraps_llm_service() -> None:
    install_tool_call_hooks()
    from pipecat.services.llm_service import LLMService

    assert getattr(LLMService._run_function_call, "_parlot_wrapped", False)


def test_any_open_session_survives_cleared_contextvar() -> None:
    """Loguru often fires on a thread without the session ContextVar."""
    provider = TracerProvider()
    set_tracer(provider.get_tracer("test"))
    set_identity("pipecat-test", "0.1.0")
    state = ensure_session("conv-logs")
    assert state is not None
    assert any_open_session() is state

    clear_active_session()
    # ContextVar cleared (other thread) but global map still has the session.
    found = any_open_session()
    assert found is state
    assert found.session_id == state.session_id
