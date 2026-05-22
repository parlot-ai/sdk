"""Tests for parlot.core.processor utilities."""

from __future__ import annotations

from opentelemetry.sdk.trace import ConcurrentMultiSpanProcessor, SpanProcessor, TracerProvider

from parlot.core.processor import assert_sync_span_processors


class _NoopProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span) -> None:
        pass


def test_assert_sync_span_processors_default_provider() -> None:
    provider = TracerProvider()
    provider.add_span_processor(_NoopProcessor())
    assert assert_sync_span_processors(provider) is True


def test_assert_sync_span_processors_rejects_concurrent() -> None:
    provider = TracerProvider()
    provider._active_span_processor = ConcurrentMultiSpanProcessor()
    provider._active_span_processor.add_span_processor(_NoopProcessor())
    assert assert_sync_span_processors(provider) is False
