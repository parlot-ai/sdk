"""Session bootstrap: ContextVar, parlot.session, event-based start."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider

from parlot.core.attrs import (
    ATTR_PARLOT_SDK_VERSION,
    ATTR_SESSION_CLOSE_ERROR,
    ATTR_SESSION_CLOSE_REASON,
    ATTR_SESSION_ID,
    ATTR_SESSION_TOTAL_INPUT_TOKENS,
    ATTR_SESSION_TOTAL_OUTPUT_TOKENS,
    ATTR_SESSION_TURN_COUNT,
    ATTR_SESSION_TURN_INDEX_MAX,
    SPAN_CONVERSATION_SESSION,
)
from parlot.core.processor import assert_sync_span_processors
from parlot.core import sdk_version as sdk_version_mod
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import (
    CLOSE_ERROR_OTLP_FLUSH_INCOMPLETE,
    _parlot_job_bootstrap,
    bootstrap_session,
    finalize_session_close_from_hook,
    get_job_bootstrap,
)
from parlot.core.session import _active_session_span
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_USER_TRANSCRIPT,
)
from bootstrap_helpers import bootstrap_via_agent_state, fire_agent_state_changed, make_mock_job_context


def _make_readable_span(name: str, attributes: dict | None = None) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.context.trace_id = 0xDEADBEEF
    span.attributes = span._attributes
    span.is_recording = MagicMock(return_value=True)
    return span


def _provider_with_processor(proc: LiveKitGenAIProcessor) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(proc)
    assert_sync_span_processors(provider)
    proc.set_tracer(provider.get_tracer("test"))
    return provider


class TestSessionBootstrap:
    def test_bootstrap_stamps_sdk_version_on_session_span(self) -> None:
        from importlib import metadata

        sdk_version_mod._cached_version = None
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        with patch.object(metadata, "version", return_value="0.1.0"):
            bootstrap_via_agent_state(proc, "AJ_sdk_ver")
            span = _active_session_span.get()
            assert span is not None
            assert span.attributes.get(ATTR_PARLOT_SDK_VERSION) == "0.1.0"

    def test_bootstrap_visible_in_entrypoint_task(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_one")
        sid = bootstrap.session_id

        child = _make_readable_span("llm_node")
        proc.on_end(child)
        assert child._attributes[ATTR_SESSION_ID] == sid

    @pytest.mark.asyncio
    async def test_bootstrap_visible_in_create_task_child(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        seen: list[str] = []

        async def run_agent_work() -> None:
            bootstrap = get_job_bootstrap()
            assert bootstrap is not None
            child = _make_readable_span("user_turn")
            proc.on_end(child)
            seen.append(child._attributes[ATTR_SESSION_ID])

        _session, parent_bootstrap = bootstrap_via_agent_state(proc, "AJ_task")
        parent_sid = parent_bootstrap.session_id
        await asyncio.create_task(run_agent_work())
        assert seen == [parent_sid]

    def test_span_enrichment_via_vendor_job_id_without_contextvar(self) -> None:
        """Production path: OTEL span callbacks may not inherit bootstrap ContextVar."""
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        vendor_job_id = "AJ_prod"
        ctx = make_mock_job_context(vendor_job_id)
        _session, bootstrap = bootstrap_via_agent_state(proc, vendor_job_id, ctx=ctx)
        sid = bootstrap.session_id

        _parlot_job_bootstrap.set(None)

        child = _make_readable_span(
            "tts_node",
            {"job_id": vendor_job_id, "lk.job_id": vendor_job_id},
        )
        proc.on_end(child)

        assert child._attributes[ATTR_SESSION_ID] == sid

    def test_close_ends_conversation_session_once(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_end")
        session_span = bootstrap.session_span
        session_span.end = MagicMock(wraps=session_span.end)

        proc.on_end(
            _make_readable_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "hi"},
            )
        )
        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")

        session_span.end.assert_called_once()
        assert get_job_bootstrap() is None

    def test_close_emits_parlot_session_close_span(self) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from parlot.core.attrs import SPAN_PARLOT_SESSION_CLOSE

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        proc = LiveKitGenAIProcessor()
        provider.add_span_processor(proc)
        assert_sync_span_processors(provider)
        proc.set_tracer(provider.get_tracer("test"))
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_close_sig")
        session_id = bootstrap.session_id
        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert len(close) == 1
        close_attrs = close[0].attributes
        assert close_attrs is not None
        assert close_attrs[ATTR_SESSION_ID] == session_id

    def test_close_span_carries_turn_count_after_user_turn(self) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from parlot.core.attrs import SPAN_PARLOT_SESSION_CLOSE

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        proc = LiveKitGenAIProcessor()
        provider.add_span_processor(proc)
        assert_sync_span_processors(provider)
        proc.set_tracer(provider.get_tracer("test"))
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_turn_ct")
        proc.on_end(
            _make_readable_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "hello"},
            )
        )
        bootstrap.state.total_input_tokens = 4143
        bootstrap.state.total_output_tokens = 317
        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert len(close) == 1
        assert close[0].attributes[ATTR_SESSION_TURN_COUNT] == 1
        assert close[0].attributes[ATTR_SESSION_TURN_INDEX_MAX] == 1
        assert close[0].attributes[ATTR_SESSION_TOTAL_INPUT_TOKENS] == 4143
        assert close[0].attributes[ATTR_SESSION_TOTAL_OUTPUT_TOKENS] == 317

    def test_close_span_stamps_flush_incomplete_when_force_flush_fails(self) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from parlot.core.attrs import SPAN_PARLOT_SESSION_CLOSE

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        proc = LiveKitGenAIProcessor()
        provider.add_span_processor(proc)
        assert_sync_span_processors(provider)
        proc.set_tracer(provider.get_tracer("test"))
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_flush_fail")

        with (
            patch(
                "parlot.instrumentation.livekit._session._force_flush_tracer_provider",
                return_value=False,
            ),
            patch("parlot.instrumentation.livekit._session.time.sleep"),
            patch(
                "parlot.instrumentation.livekit._session._CLOSE_FLUSH_BUDGET_S",
                0.05,
            ),
            patch(
                "parlot.instrumentation.livekit._session._CLOSE_FLUSH_BACKOFFS_S",
                (0.01,),
            ),
        ):
            finalize_session_close_from_hook(bootstrap, close_reason="clean_close")

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert len(close) == 1
        assert (
            close[0].attributes[ATTR_SESSION_CLOSE_ERROR]
            == CLOSE_ERROR_OTLP_FLUSH_INCOMPLETE
        )

    def test_close_span_preserves_framework_close_error_over_flush_incomplete(
        self,
    ) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from parlot.core.attrs import SPAN_PARLOT_SESSION_CLOSE

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        proc = LiveKitGenAIProcessor()
        provider.add_span_processor(proc)
        assert_sync_span_processors(provider)
        proc.set_tracer(provider.get_tracer("test"))
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_flush_keep")

        with (
            patch(
                "parlot.instrumentation.livekit._session._force_flush_tracer_provider",
                return_value=False,
            ),
            patch("parlot.instrumentation.livekit._session.time.sleep"),
            patch(
                "parlot.instrumentation.livekit._session._CLOSE_FLUSH_BUDGET_S",
                0.05,
            ),
            patch(
                "parlot.instrumentation.livekit._session._CLOSE_FLUSH_BACKOFFS_S",
                (0.01,),
            ),
        ):
            finalize_session_close_from_hook(
                bootstrap,
                close_reason="error",
                close_error="room_disconnected",
            )

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert close[0].attributes[ATTR_SESSION_CLOSE_ERROR] == "room_disconnected"

    def test_close_span_includes_close_reason(self) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from parlot.core.attrs import SPAN_PARLOT_SESSION_CLOSE

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        proc = LiveKitGenAIProcessor()
        provider.add_span_processor(proc)
        assert_sync_span_processors(provider)
        proc.set_tracer(provider.get_tracer("test"))
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_reason")
        finalize_session_close_from_hook(bootstrap, close_reason="user_hangup")

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert close[0].attributes[ATTR_SESSION_CLOSE_REASON] == "user_hangup"

    def test_missing_bootstrap_no_session_id_minted(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_readable_span("llm_node")
        proc.on_end(span)
        assert ATTR_SESSION_ID not in span._attributes

    def test_two_jobs_two_session_ids(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        _s1, b1 = bootstrap_via_agent_state(proc, "J1")
        s1 = b1.session_id
        finalize_session_close_from_hook(b1, close_reason="clean_close")
        _s2, b2 = bootstrap_via_agent_state(proc, "J2")
        s2 = b2.session_id
        finalize_session_close_from_hook(b2, close_reason="clean_close")
        assert s1 != s2

    @pytest.mark.asyncio
    async def test_connect_hook_stamps_room_sid(self) -> None:
        from parlot.instrumentation.livekit._session import refresh_bootstrap_room_from_ctx

        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        ctx = make_mock_job_context("AJ_room")
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_room", ctx=ctx)

        class _Room:
            async def sid(self) -> str:
                return "RM_connect"

        class _Ctx:
            _connected = True
            job = ctx.job
            room = _Room()

        await refresh_bootstrap_room_from_ctx(_Ctx())
        assert bootstrap.state.room_sid == "RM_connect"

    @pytest.mark.asyncio
    async def test_finalize_close_from_different_task_skips_detach(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)

        async def run_bootstrap():
            return bootstrap_via_agent_state(proc, "AJ_x_task")

        _session, bootstrap = await asyncio.create_task(run_bootstrap())
        attach_task = bootstrap.attach_task
        assert attach_task is not None

        async def close_from_other_task() -> None:
            finalize_session_close_from_hook(bootstrap, close_reason="participant_left")

        await asyncio.create_task(close_from_other_task())
        assert bootstrap.close_span_done is True
        assert get_job_bootstrap() is None
        assert asyncio.current_task() is not attach_task

    def test_shutdown_reset_does_not_rebootstrap(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        from parlot.instrumentation.livekit._events import LiveKitEventBridge

        ctx = make_mock_job_context("AJ_shutdown")
        session, bootstrap = bootstrap_via_agent_state(proc, "AJ_shutdown", ctx=ctx)
        first_sid = bootstrap.session_id

        bridge = LiveKitEventBridge(proc, proc._tracer)
        bridge._session = session
        fire_agent_state_changed(bridge, "listening", "initializing")
        fire_agent_state_changed(bridge, "initializing", "listening")

        assert get_job_bootstrap() is not None
        assert get_job_bootstrap().session_id == first_sid

    def test_bootstrap_session_idempotent(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        bootstrap_session(proc, vendor_job_id="AJ_dup")
        first = get_job_bootstrap()
        assert first is not None
        bootstrap_session(proc, vendor_job_id="AJ_other")
        assert get_job_bootstrap() is first

    def test_early_conversation_session_end_applies_aggregates(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        _session, bootstrap = bootstrap_via_agent_state(proc, "AJ_early")
        proc.on_end(
            _make_readable_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "cancel please"},
            )
        )
        assert bootstrap.aggregates_applied is False

        proc.on_end(_make_readable_span(SPAN_CONVERSATION_SESSION))
        assert bootstrap.aggregates_applied is True
        assert get_job_bootstrap() is not None

        finalize_session_close_from_hook(bootstrap, close_reason="clean_close")
        assert get_job_bootstrap() is None

    @pytest.mark.asyncio
    async def test_post_bootstrap_connect_scheduled_after_event_start(self) -> None:
        from unittest.mock import AsyncMock

        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        ctx = make_mock_job_context("AJ_egress")

        with patch(
            "parlot.instrumentation.livekit._session._run_post_bootstrap_connect",
            new_callable=AsyncMock,
        ) as mock_run:
            bootstrap_via_agent_state(proc, "AJ_egress", ctx=ctx)
            await asyncio.sleep(0)
            mock_run.assert_awaited_once_with(ctx)
