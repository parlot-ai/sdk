"""Mint ``parlot.turn`` from Pipecat context-aggregator turn events.

``LLMUserAggregator`` / ``LLMAssistantAggregator`` fire committed transcripts
on ``on_user_turn_stopped`` / ``on_assistant_turn_stopped`` (and realtime
``on_user_turn_message_added``). Those are the sole source of contract turns
after ``parlotize()`` — OTEL STT/LLM/TTS spans only nest under turn indices.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from ._session import (
    allocate_agent_turn_index,
    allocate_user_turn_index,
    any_open_session,
    clear_open_turn_indices,
    emit_turn,
)

logger = logging.getLogger("parlot.instrumentation.pipecat")


def _iso_to_unix_ns(ts: str | None) -> int | None:
    if not ts or not str(ts).strip():
        return None
    raw = str(ts).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1_000_000_000)
    except (TypeError, ValueError):
        return None


def _resolve_state():
    return any_open_session()


def handle_user_turn_stopped(_aggregator: Any, _strategy: Any, message: Any) -> None:
    """``on_user_turn_stopped`` — cascade mode has content; realtime is ``None``."""
    content = getattr(message, "content", None)
    if content is None:
        # Realtime: wait for on_user_turn_message_added.
        return
    text = str(content).strip()
    if not text:
        return
    _mint_user_turn(text, timestamp=getattr(message, "timestamp", None))


def handle_user_turn_message_added(_aggregator: Any, message: Any) -> None:
    """``on_user_turn_message_added`` — always has content (realtime user text)."""
    content = getattr(message, "content", None)
    if content is None:
        return
    text = str(content).strip()
    if not text:
        return
    _mint_user_turn(text, timestamp=getattr(message, "timestamp", None))


def handle_assistant_turn_stopped(_aggregator: Any, message: Any) -> None:
    """``on_assistant_turn_stopped`` — spoken (or interrupted) assistant text."""
    content = getattr(message, "content", None)
    text = str(content or "").strip()
    if not text:
        return
    interrupted = bool(getattr(message, "interrupted", False))
    state = _resolve_state()
    if state is None:
        logger.debug("parlot: assistant turn stopped with no open session")
        return
    if state.agent_turn_emitted and state.open_agent_turn_index is not None:
        return

    turn_index = allocate_agent_turn_index(state)
    start_ns = _iso_to_unix_ns(getattr(message, "timestamp", None))
    end_ns = time.time_ns()
    if start_ns is not None and end_ns < start_ns:
        end_ns = start_ns + 1

    emit_turn(
        state,
        turn_index=turn_index,
        role="agent",
        interrupted=interrupted,
        agent_text=text,
        start_time_ns=start_ns,
        end_time_ns=end_ns if start_ns is not None else None,
    )
    state.agent_turn_emitted = True
    clear_open_turn_indices(state)


def _mint_user_turn(text: str, *, timestamp: str | None) -> None:
    state = _resolve_state()
    if state is None:
        logger.debug("parlot: user turn stopped with no open session")
        return
    if state.user_turn_emitted and state.open_user_turn_index is not None:
        return

    user_idx = allocate_user_turn_index(state)
    allocate_agent_turn_index(state)  # reserve agent slot for nesting + reply
    start_ns = _iso_to_unix_ns(timestamp)
    end_ns = time.time_ns()
    if start_ns is not None and end_ns < start_ns:
        end_ns = start_ns + 1

    emit_turn(
        state,
        turn_index=user_idx,
        role="user",
        user_text=text,
        start_time_ns=start_ns,
        end_time_ns=end_ns if start_ns is not None else None,
    )
    state.user_turn_emitted = True
    state.agent_turn_emitted = False
