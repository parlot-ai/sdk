"""parlotize(await_recording=…) connect-time bootstrap + egress await."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider

from bootstrap_helpers import fire_agent_state_changed, make_mock_job_context
from parlot.core.context import ParlotContext
from parlot.core.processor import assert_sync_span_processors
from parlot.core.runtime import ParlotRuntimeContext
from parlot.instrumentation.livekit import _auto
from parlot.instrumentation.livekit._events import LiveKitEventBridge
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import (
    _parlot_job_bootstrap,
    get_job_bootstrap,
)


@pytest.fixture(autouse=True)
def _reset_await_recording_state():
    token = _parlot_job_bootstrap.set(None)
    _auto.set_configured_context(None)
    _auto._configured_record = None
    _auto._configured_await_recording = False
    _auto._configured_processor = None
    _auto._configured_agent_id = "test-agent"
    yield
    _parlot_job_bootstrap.reset(token)
    _auto.set_configured_context(None)
    _auto._configured_record = None
    _auto._configured_await_recording = False
    _auto._configured_processor = None
    _auto._configured_agent_id = None


def _provider_with_processor(proc: LiveKitGenAIProcessor) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(proc)
    assert_sync_span_processors(provider)
    proc.set_tracer(provider.get_tracer("test"))
    return provider


def _runtime() -> ParlotRuntimeContext:
    return ParlotRuntimeContext(
        endpoint="https://ingest.test",
        api_key="key",
        tenant_id="org-1",
        content_bucket="bucket",
        r2_endpoint="https://r2.example.com",
    )


def _ctx_with_record(*, record: bool = True) -> SimpleNamespace:
    ctx = make_mock_job_context("AJ_await", room_name="room-1", room_sid="RM_1")
    ctx.job = SimpleNamespace(
        id="AJ_await",
        room=SimpleNamespace(name="room-1", sid="RM_1"),
        metadata=f'{{"record": {str(record).lower()}}}',
        agent_name="agent",
        dispatch_id=None,
    )
    return ctx


@pytest.mark.asyncio
async def test_await_recording_false_does_not_bootstrap_on_connect() -> None:
    proc = LiveKitGenAIProcessor()
    _provider_with_processor(proc)
    _auto._configured_processor = proc
    _auto._configured_await_recording = False
    _auto._configured_record = True
    context = ParlotContext()
    context.runtime = _runtime()
    _auto.set_configured_context(context)

    with patch(
        "parlot.instrumentation.livekit._session._run_post_bootstrap_connect",
        new_callable=AsyncMock,
    ) as mock_run:
        await _auto._run_connect_recording_side_effects(_ctx_with_record())

    assert get_job_bootstrap() is None
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_await_recording_true_bootstraps_and_awaits_egress() -> None:
    proc = LiveKitGenAIProcessor()
    _provider_with_processor(proc)
    _auto._configured_processor = proc
    _auto._configured_await_recording = True
    _auto._configured_record = True
    context = ParlotContext()
    context.runtime = _runtime()
    _auto.set_configured_context(context)

    with patch(
        "parlot.instrumentation.livekit._session._run_post_bootstrap_connect",
        new_callable=AsyncMock,
    ) as mock_run:
        await _auto._run_connect_recording_side_effects(_ctx_with_record())

    bootstrap = get_job_bootstrap()
    assert bootstrap is not None
    assert bootstrap.state.session_id == "AJ_await"
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_await_recording_true_record_off_skips_bootstrap() -> None:
    proc = LiveKitGenAIProcessor()
    _provider_with_processor(proc)
    _auto._configured_processor = proc
    _auto._configured_await_recording = True
    _auto._configured_record = False
    context = ParlotContext()
    context.runtime = _runtime()
    _auto.set_configured_context(context)

    with patch(
        "parlot.instrumentation.livekit._session._run_post_bootstrap_connect",
        new_callable=AsyncMock,
    ) as mock_run:
        await _auto._run_connect_recording_side_effects(_ctx_with_record(record=False))

    assert get_job_bootstrap() is None
    mock_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_events_path_skips_when_connect_already_bootstrapped() -> None:
    """Listening fallback must not mint a second session after await_recording."""
    proc = LiveKitGenAIProcessor()
    _provider_with_processor(proc)
    _auto._configured_processor = proc
    _auto._configured_await_recording = True
    _auto._configured_record = True
    context = ParlotContext()
    context.runtime = _runtime()
    _auto.set_configured_context(context)

    ctx = _ctx_with_record()
    with patch(
        "parlot.instrumentation.livekit._session._run_post_bootstrap_connect",
        new_callable=AsyncMock,
    ):
        await _auto._run_connect_recording_side_effects(ctx)

    first = get_job_bootstrap()
    assert first is not None

    session = SimpleNamespace(
        _parlot_job_ctx=ctx,
        _parlot_shutdown_reset=False,
        _parlot_bootstrapped=False,
        room=None,
        on=lambda *_a, **_k: (lambda fn: fn),
    )
    bridge = LiveKitEventBridge(proc, proc._tracer)
    bridge._session = session

    with patch(
        "parlot.instrumentation.livekit._session.schedule_post_bootstrap_connect"
    ) as mock_schedule:
        fire_agent_state_changed(bridge, "initializing", "listening")
        mock_schedule.assert_not_called()

    assert get_job_bootstrap() is first


def test_configured_await_recording_getter() -> None:
    assert _auto.configured_await_recording() is False
    _auto._configured_await_recording = True
    assert _auto.configured_await_recording() is True
