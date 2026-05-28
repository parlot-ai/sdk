"""Session bootstrap: ContextVar, conversation.session, span processor guard."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import TracerProvider

from parlot.core.attrs import (
    ATTR_SESSION_CLOSE_REASON,
    ATTR_SESSION_ID,
    ATTR_SESSION_TURN_COUNT,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import (
    SPAN_CONVERSATION_SESSION,
    get_job_bootstrap,
    handle_conversation_session_on_end,
)
from parlot.core.processor import assert_sync_span_processors
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_JOB_ID,
    ATTR_LK_ROOM_SID,
    ATTR_LK_USER_TRANSCRIPT,
)


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
    def test_bootstrap_visible_in_entrypoint_task(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_one"})
        proc.on_start(entry)
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
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

        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_task"})
        proc.on_start(entry)
        parent_bootstrap = get_job_bootstrap()
        assert parent_bootstrap is not None
        parent_sid = parent_bootstrap.session_id
        await asyncio.create_task(run_agent_work())
        assert seen == [parent_sid]

    def test_teardown_ends_conversation_session_once(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_end"})
        proc.on_start(entry)
        bootstrap = get_job_bootstrap()
        session_span = bootstrap.session_span
        session_span.end = MagicMock(wraps=session_span.end)

        proc.on_end(
            _make_readable_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "hi"},
            )
        )
        proc.on_end(entry)

        session_span.end.assert_called_once()
        assert get_job_bootstrap() is None

    def test_teardown_emits_parlot_session_close_span(self) -> None:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        from parlot.core.attrs import ATTR_SESSION_ID, SPAN_PARLOT_SESSION_CLOSE

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        proc = LiveKitGenAIProcessor()
        provider.add_span_processor(proc)
        assert_sync_span_processors(provider)
        proc.set_tracer(provider.get_tracer("test"))
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_close_sig"})
        proc.on_start(entry)
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        session_id = bootstrap.session_id
        proc.on_end(entry)

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
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_turn_ct"})
        proc.on_start(entry)
        proc.on_end(
            _make_readable_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "hello"},
            )
        )
        proc.on_end(entry)

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert len(close) == 1
        assert close[0].attributes[ATTR_SESSION_TURN_COUNT] == 1

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
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_reason"})
        proc.on_start(entry)
        proc.on_end(entry)

        close = [
            s
            for s in exporter.get_finished_spans()
            if s.name == SPAN_PARLOT_SESSION_CLOSE
        ]
        assert close[0].attributes[ATTR_SESSION_CLOSE_REASON] == "clean_close"

    def test_missing_bootstrap_no_session_id_minted(self) -> None:
        proc = LiveKitGenAIProcessor()
        span = _make_readable_span("llm_node")
        proc.on_end(span)
        assert ATTR_SESSION_ID not in span._attributes

    def test_two_jobs_two_session_ids(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        e1 = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "J1"})
        e2 = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "J2"})
        proc.on_start(e1)
        b1 = get_job_bootstrap()
        assert b1 is not None
        s1 = b1.session_id
        proc.on_end(e1)
        proc.on_start(e2)
        b2 = get_job_bootstrap()
        assert b2 is not None
        s2 = b2.session_id
        proc.on_end(e2)
        assert s1 != s2

    @pytest.mark.asyncio
    async def test_connect_hook_stamps_room_sid(self) -> None:
        from parlot.instrumentation.livekit._session import refresh_bootstrap_room_from_ctx

        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_room"})
        proc.on_start(entry)
        bootstrap = get_job_bootstrap()

        class _Room:
            async def sid(self) -> str:
                return "RM_connect"

        class _Ctx:
            _connected = True
            job = MagicMock(id="AJ_room", room=None)
            room = _Room()

        await refresh_bootstrap_room_from_ctx(_Ctx())
        assert bootstrap.state.room_sid == "RM_connect"
        attrs = getattr(bootstrap.session_span, "_attributes", {}) or {}
        if hasattr(bootstrap.session_span, "attributes"):
            attrs = bootstrap.session_span.attributes or attrs
        assert bootstrap.state.room_sid == "RM_connect"

    def test_early_conversation_session_end_applies_aggregates(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_early"})
        proc.on_start(entry)
        proc.on_end(
            _make_readable_span(
                "user_turn",
                {ATTR_LK_USER_TRANSCRIPT: "cancel please"},
            )
        )
        bootstrap = get_job_bootstrap()
        assert bootstrap is not None
        assert bootstrap.aggregates_applied is False

        proc.on_end(_make_readable_span(SPAN_CONVERSATION_SESSION))
        assert bootstrap.aggregates_applied is True
        assert get_job_bootstrap() is not None

        proc.on_end(entry)
        assert get_job_bootstrap() is None
