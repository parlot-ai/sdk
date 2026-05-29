"""Tests for parlot.core.processor utilities."""

from __future__ import annotations

import logging as stdlib_logging
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace import ConcurrentMultiSpanProcessor, SpanProcessor, TracerProvider

from parlot.core.processor import ParlotBaseProcessor, assert_sync_span_processors


class _NoopProcessor(SpanProcessor):
    def on_start(self, span, parent_context=None) -> None:
        pass

    def on_end(self, span) -> None:
        pass


class _SubclassProcessor(ParlotBaseProcessor):
    def on_start(self, span, parent_context=None) -> None:
        super().on_start(span, parent_context)

    def on_end(self, span) -> None:
        super().on_end(span)


def test_assert_sync_span_processors_default_provider() -> None:
    provider = TracerProvider()
    provider.add_span_processor(_NoopProcessor())
    assert assert_sync_span_processors(provider) is True


def test_assert_sync_span_processors_rejects_concurrent() -> None:
    provider = TracerProvider()
    provider._active_span_processor = ConcurrentMultiSpanProcessor()
    provider._active_span_processor.add_span_processor(_NoopProcessor())
    assert assert_sync_span_processors(provider) is False


def test_subclass_super_on_start_logs_when_debug() -> None:
    from parlot.core import logging as parlot_logging

    parlot_logging.logger.setLevel(stdlib_logging.DEBUG)
    proc = _SubclassProcessor()
    span = MagicMock()
    span.name = "test"
    span.context = None
    span.attributes = {}
    with patch.object(parlot_logging.logger, "debug") as mock_debug:
        proc.on_start(span)
        mock_debug.assert_called_once()


def test_subclass_super_on_end_logs_when_debug() -> None:
    from parlot.core import logging as parlot_logging

    parlot_logging.logger.setLevel(stdlib_logging.DEBUG)
    proc = _SubclassProcessor()
    span = MagicMock()
    span.name = "test"
    span.context = None
    span.attributes = {}
    with patch.object(parlot_logging.logger, "debug") as mock_debug:
        proc.on_end(span)
        mock_debug.assert_called_once()
