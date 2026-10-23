"""Tests for parlot.core.logging."""

from __future__ import annotations

import logging as stdlib_logging
import os
from unittest.mock import MagicMock, patch

from parlot.core import logging as parlot_logging
from parlot.core.parlotize import configure_parlot_logging


def test_configure_parlot_logging_debug_does_not_raise_root(monkeypatch) -> None:
    monkeypatch.setenv("PARLOT_DEBUG_LEVEL", "DEBUG")
    # Simulate a process that already has a root handler (e.g. pipecat runner).
    root = stdlib_logging.getLogger()
    had_handler = bool(root.handlers)
    if not had_handler:
        handler = stdlib_logging.StreamHandler()
        root.addHandler(handler)
    try:
        root.setLevel(stdlib_logging.INFO)
        configure_parlot_logging()
        assert root.level == stdlib_logging.INFO
        assert stdlib_logging.getLogger("parlot").level == stdlib_logging.DEBUG
        assert stdlib_logging.getLogger("parlot.instrumentation.pipecat").level == (
            stdlib_logging.DEBUG
        )
        # Third-party noise stays inherit/root INFO — not forced to DEBUG.
        assert stdlib_logging.getLogger("websockets").level == stdlib_logging.NOTSET
        assert stdlib_logging.getLogger("aiortc").level == stdlib_logging.NOTSET
    finally:
        if not had_handler:
            root.handlers.clear()
        os.environ.pop("PARLOT_DEBUG_LEVEL", None)


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


def test_format_attrs_for_log_trims_long_strings():
    long_ctx = "x" * 500
    formatted = parlot_logging.format_attrs_for_log({"lk.chat_ctx": long_ctx})
    assert "(+468)" in formatted
    assert long_ctx not in formatted
    assert len(formatted) < len(long_ctx)
    assert formatted.startswith('{"lk.chat_ctx": "')
