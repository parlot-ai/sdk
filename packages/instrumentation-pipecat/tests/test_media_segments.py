"""Turn speech_wall / media_segment stamping from recording anchor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from parlot.core.attrs import (
    ATTR_TURN_MEDIA_END_MS,
    ATTR_TURN_MEDIA_START_MS,
    ATTR_TURN_SPEECH_WALL_END_MS,
    ATTR_TURN_SPEECH_WALL_START_MS,
)
from parlot.instrumentation.pipecat._session import (
    _PipecatSessionState,
    emit_turn,
    set_identity,
    set_tracer,
)


def test_emit_turn_stamps_media_segments_from_anchor() -> None:
    set_identity("agent", "0.1.0")
    tracer = MagicMock()
    span = MagicMock()
    # start_as_current_span context manager
    cm = MagicMock()
    cm.__enter__.return_value = span
    cm.__exit__.return_value = None
    tracer.start_as_current_span.return_value = cm
    # Also support start_span path used by emit_parlot_turn_root
    tracer.start_span.return_value = span
    set_tracer(tracer)

    state = _PipecatSessionState(
        session_id="s" * 32,
        conversation_id="c" * 32,
        framework="pipecat",
        recording_anchor_wall_ms=1_000_000,
    )
    with patch(
        "parlot.instrumentation.pipecat._session.emit_parlot_turn_root"
    ) as emit:
        emit.return_value = ("trace", "span")
        emit_turn(
            state,
            turn_index=1,
            role="user",
            user_text="hi",
            start_time_ns=1_000_500_000_000,
            end_time_ns=1_001_000_000_000,
        )
        kwargs = emit.call_args.kwargs
        extra = kwargs["extra_attrs"]
        assert extra[ATTR_TURN_SPEECH_WALL_START_MS] == 1_000_500
        assert extra[ATTR_TURN_SPEECH_WALL_END_MS] == 1_001_000
        assert extra[ATTR_TURN_MEDIA_START_MS] == 500
        assert extra[ATTR_TURN_MEDIA_END_MS] == 1000
