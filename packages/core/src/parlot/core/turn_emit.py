"""Shared helpers for stamping committed turn utterance text onto ``parlot.turn`` spans."""

from __future__ import annotations

from typing import Any

from parlot.core.attrs import ATTR_TURN_AGENT_TEXT, ATTR_TURN_USER_TEXT


def stamp_turn_utterance_text(
    span: Any,
    *,
    participant_role: str,
    utterance_text: str,
) -> None:
    """
    Stamp ``turn.user_text`` or ``turn.agent_text`` on a turn root span.

    LiveKit and LangGraph adapters both call this after committing an utterance
    so the OTLP contract stays consistent regardless of source.
    """
    text = (utterance_text or "").strip()
    if not text:
        return
    role = (participant_role or "").strip().lower()
    if role == "user":
        span.set_attribute(ATTR_TURN_USER_TEXT, text)
    elif role == "agent":
        span.set_attribute(ATTR_TURN_AGENT_TEXT, text)
