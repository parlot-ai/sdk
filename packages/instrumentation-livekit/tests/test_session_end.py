"""on_session_end: SessionReport recording anchor after deferred teardown."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from parlot.core.attrs import ATTR_SESSION_RECORDING_ANCHOR_WALL_MS
from parlot.core.processor import assert_sync_span_processors
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import (
    finalize_deferred_session_end,
    get_job_bootstrap,
)
from parlot.instrumentation.livekit._session_end import handle_session_end
from parlot.instrumentation.livekit.attrs import ATTR_LK_JOB_ID
from opentelemetry.sdk.trace import TracerProvider


def _make_readable_span(name: str, attributes: dict | None = None) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.context.trace_id = 0xDEADBEEF
    span.attributes = span._attributes
    return span


def _provider_with_processor(proc: LiveKitGenAIProcessor) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(proc)
    assert_sync_span_processors(provider)
    proc.set_tracer(provider.get_tracer("test"))
    return provider


class TestSessionEnd:
    @pytest.mark.asyncio
    async def test_handle_session_end_sets_recording_anchor(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_anchor"})
        proc.on_start(entry)
        bootstrap = get_job_bootstrap()
        session_span = bootstrap.session_span
        session_span.end = MagicMock(wraps=session_span.end)

        proc.on_end(entry)
        assert get_job_bootstrap() is None

        report = MagicMock()
        report.audio_recording_started_at = 1_700_000_000.5

        ctx = MagicMock()
        ctx.job = MagicMock(id="AJ_anchor")
        ctx.make_session_report = MagicMock(return_value=report)

        await handle_session_end(ctx)

        attrs = getattr(session_span, "_attributes", {}) or {}
        if hasattr(session_span, "attributes"):
            attrs = session_span.attributes or attrs
        assert attrs.get(ATTR_SESSION_RECORDING_ANCHOR_WALL_MS) == 1_700_000_000_500
        session_span.end.assert_called_once()

    def test_finalize_without_report_ends_span(self) -> None:
        proc = LiveKitGenAIProcessor()
        _provider_with_processor(proc)
        entry = _make_readable_span("job_entrypoint", {ATTR_LK_JOB_ID: "AJ_no_report"})
        proc.on_start(entry)
        session_span = get_job_bootstrap().session_span
        session_span.end = MagicMock(wraps=session_span.end)

        proc.on_end(entry)
        finalize_deferred_session_end(job_id="AJ_no_report", report=None)
        session_span.end.assert_called_once()
