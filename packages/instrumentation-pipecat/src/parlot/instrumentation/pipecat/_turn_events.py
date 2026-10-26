"""Mint ``parlot.turn`` from Pipecat context-aggregator turn events.

``LLMUserAggregator`` / ``LLMAssistantAggregator`` fire committed transcripts
on ``on_user_turn_stopped`` / ``on_assistant_turn_stopped`` (and realtime
``on_user_turn_message_added``). Those are the sole source of contract turns
after ``parlotize()`` — OTEL STT/LLM/TTS spans only nest under turn indices.

``on_*_turn_started`` reserves indices early for waterfall nesting and records
sharper start times. ``UserBotLatencyObserver.on_latency_measured`` buffers
user→bot latency onto the next agent ``parlot.turn``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

from ._session import (
    allocate_agent_turn_index,
    allocate_user_turn_index,
    any_open_session,
    buffer_e2e_latency,
    clear_open_turn_indices,
    emit_turn,
    take_pending_e2e_latency,
)

logger = logging.getLogger("parlot.instrumentation.pipecat")

F = TypeVar("F", bound=Callable[..., Any])


def _fail_soft(fn: F) -> F:
    """Never let Parlot turn handlers break user handlers or the pipeline."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.debug("parlot: turn event handler failed", exc_info=True)

    return wrapper  # type: ignore[return-value]


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


def _prefer_start_ns(recorded: int | None, timestamp: str | None) -> int | None:
    if recorded is not None:
        return recorded
    return _iso_to_unix_ns(timestamp)


@_fail_soft
def handle_latency_measured(_observer: Any, latency_seconds: float) -> None:
    """``UserBotLatencyObserver.on_latency_measured`` — buffer for next agent turn."""
    try:
        latency = float(latency_seconds)
    except (TypeError, ValueError):
        return
    state = _resolve_state()
    if state is None:
        return
    buffer_e2e_latency(state, latency)


@_fail_soft
def handle_user_turn_started(_aggregator: Any, _strategy: Any = None) -> None:
    """``on_user_turn_started`` — reserve indices + speech start for nesting."""
    state = _resolve_state()
    if state is None:
        return
    allocate_user_turn_index(state)
    allocate_agent_turn_index(state)
    if state.user_turn_start_ns is None:
        state.user_turn_start_ns = time.time_ns()


@_fail_soft
def handle_assistant_turn_started(_aggregator: Any) -> None:
    """``on_assistant_turn_started`` — reserve agent index + speech start."""
    state = _resolve_state()
    if state is None:
        return
    allocate_agent_turn_index(state)
    if state.agent_turn_start_ns is None:
        state.agent_turn_start_ns = time.time_ns()


@_fail_soft
def handle_user_turn_stopped(_aggregator: Any, _strategy: Any, message: Any) -> None:
    """``on_user_turn_stopped`` — cascade mode has content; realtime is ``None``."""
    content = getattr(message, "content", None)
    if content is None:
        # Realtime: wait for on_user_turn_message_added.
        return
    text = str(content).strip()
    if not text:
        # Empty / timeout noise after started — drop reserved indices.
        state = _resolve_state()
        if state is not None and not state.user_turn_emitted:
            clear_open_turn_indices(state)
        return
    _mint_user_turn(text, timestamp=getattr(message, "timestamp", None))


@_fail_soft
def handle_user_turn_message_added(_aggregator: Any, message: Any) -> None:
    """``on_user_turn_message_added`` — always has content (realtime user text)."""
    content = getattr(message, "content", None)
    if content is None:
        return
    text = str(content).strip()
    if not text:
        return
    _mint_user_turn(text, timestamp=getattr(message, "timestamp", None))


@_fail_soft
def handle_assistant_turn_stopped(_aggregator: Any, message: Any) -> None:
    """``on_assistant_turn_stopped`` — spoken (or interrupted) assistant text."""
    content = getattr(message, "content", None)
    text = str(content or "").strip()
    state = _resolve_state()
    if state is None:
        logger.debug("parlot: assistant turn stopped with no open session")
        return
    if not text:
        # Interrupted before tokens — drop reservation; keep any pending e2e.
        if not state.agent_turn_emitted:
            clear_open_turn_indices(state)
        return
    if state.agent_turn_emitted and state.open_agent_turn_index is not None:
        return

    turn_index = allocate_agent_turn_index(state)
    start_ns = _prefer_start_ns(
        state.agent_turn_start_ns, getattr(message, "timestamp", None)
    )
    end_ns = time.time_ns()
    if start_ns is not None and end_ns < start_ns:
        end_ns = start_ns + 1
    e2e = take_pending_e2e_latency(state)

    emit_turn(
        state,
        turn_index=turn_index,
        role="agent",
        interrupted=bool(getattr(message, "interrupted", False)),
        e2e_latency_s=e2e,
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
    start_ns = _prefer_start_ns(state.user_turn_start_ns, timestamp)
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
