"""Recording timeline anchors and GenAI content capture policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

from opentelemetry.sdk.trace import ReadableSpan

from ._session_state import _LiveKitSessionState

if TYPE_CHECKING:
    from parlot.core.context import ParlotContext

ActiveAgentIdFn = Callable[..., str]


class RecordingCoordinator:
    """Owns recording anchor / media segment math and GenAI content gating."""

    def __init__(
        self,
        *,
        get_capture_override: Callable[[], Optional[bool]],
        active_agent_id_fn: ActiveAgentIdFn,
        get_context: Callable[[], ParlotContext] | None = None,
    ) -> None:
        self._get_capture_override = get_capture_override
        self._active_agent_id_fn = active_agent_id_fn
        self._get_context = get_context

    def set_recording_anchor_wall_ms(
        self, state: _LiveKitSessionState, anchor_wall_ms: int
    ) -> None:
        """Recording timeline t=0 (``audio_recording_started_at``) for media_segment_*."""
        if anchor_wall_ms <= 0:
            return
        from parlot.core.recording_timeline import set_recording_anchor_wall_ms

        set_recording_anchor_wall_ms(state, anchor_wall_ms)

    @staticmethod
    def speech_wall_ms_from_span(span: ReadableSpan) -> tuple[int, int] | None:
        """Wall-clock epoch ms from OTLP span bounds (LiveKit user_turn / agent_turn)."""
        from parlot.core.recording_timeline import speech_wall_ms_from_span

        return speech_wall_ms_from_span(span)

    @staticmethod
    def media_segments_from_speech(
        state: _LiveKitSessionState,
        speech_start_wall_ms: int,
        speech_end_wall_ms: int,
    ) -> tuple[int, int]:
        from parlot.core.recording_timeline import media_segments_from_speech

        if getattr(state, "recording_anchor_wall_ms", None) is None:
            return 0, 0
        return media_segments_from_speech(
            state, speech_start_wall_ms, speech_end_wall_ms
        )

    def genai_content_enabled(
        self,
        state: _LiveKitSessionState | None = None,
        *,
        capture_override: Optional[bool] = None,
        active_agent_id_fn: ActiveAgentIdFn | None = None,
    ) -> bool:
        override = (
            capture_override
            if capture_override is not None
            else self._get_capture_override()
        )
        if override is not None:
            return override
        from ._recording_guard import should_capture_genai_content

        resolve_agent = active_agent_id_fn or self._active_agent_id_fn
        agent_id = ""
        if state is not None:
            agent_id = resolve_agent(state, {})
            if agent_id == "unknown":
                agent_id = ""
        context = self._get_context() if self._get_context is not None else None
        return should_capture_genai_content(agent_id=agent_id, context=context)
