"""Tests for parlot.core.logging."""

from __future__ import annotations

import logging as stdlib_logging
from unittest.mock import MagicMock, patch

from parlot.core import logging as parlot_logging


def test_is_parlot_debug_defaults_to_info():
    parlot_logging.logger.setLevel(stdlib_logging.INFO)
    assert parlot_logging.is_parlot_debug() is False


def test_is_parlot_debug_true_when_debug():
    parlot_logging.logger.setLevel(stdlib_logging.DEBUG)
    assert parlot_logging.is_parlot_debug() is True


def test_log_span_event_skips_when_not_debug():
    span = MagicMock()
    parlot_logging.logger.setLevel(stdlib_logging.INFO)
    with patch.object(parlot_logging.logger, "debug") as mock_debug:
        parlot_logging.log_span_event("on_start", span)
        mock_debug.assert_not_called()


def test_log_span_event_logs_when_debug():
    span = MagicMock()
    span.name = "test_span"
    span.context = None
    span.attributes = {}
    parlot_logging.logger.setLevel(stdlib_logging.DEBUG)
    with patch.object(parlot_logging.logger, "debug") as mock_debug:
        parlot_logging.log_span_event("on_start", span)
        mock_debug.assert_called_once()
        assert mock_debug.call_args[0][0] == "%s"
        assert "on_start" in mock_debug.call_args[0][1]
        assert "test_span" in mock_debug.call_args[0][1]
