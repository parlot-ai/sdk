"""Conversation/thread-keyed session registry shared by Pipecat and LangGraph."""

from __future__ import annotations

import atexit
import logging
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from opentelemetry.trace import Span

from parlot.core.session import (
    SessionState,
    clear_active_session,
    get_active_session,
    set_active_session,
)
from parlot.core.session_lifecycle import end_session_span_ok

logger = logging.getLogger("parlot.core.session_registry")

S = TypeVar("S", bound=SessionState)


@dataclass
class ConversationSessionRegistry(Generic[S]):
    """Keyed map of open ``parlot.session`` spans + framework session state.

    Used by conversation/thread-scoped adapters (Pipecat, LangGraph). LiveKit
    keeps its job ContextVar bootstrap and does not use this registry.
    """

    _sessions: dict[str, tuple[Span, S]] = field(default_factory=dict)
    _atexit_registered: bool = False
    _atexit_reason: str = "process_exit"

    def get(self, key: str) -> tuple[Span, S] | None:
        return self._sessions.get(key)

    def get_state(self, key: str) -> S | None:
        pair = self._sessions.get(key)
        return pair[1] if pair else None

    def keys(self) -> list[str]:
        return list(self._sessions)

    def values(self) -> list[tuple[Span, S]]:
        return list(self._sessions.values())

    def __len__(self) -> int:
        return len(self._sessions)

    def __bool__(self) -> bool:
        return bool(self._sessions)

    def last_opened_state(self) -> S | None:
        """Insertion-order last session (single-bot local runners)."""
        if not self._sessions:
            return None
        _span, state = next(reversed(list(self._sessions.values())))
        return state

    def put(self, key: str, span: Span, state: S) -> None:
        self._sessions[key] = (span, state)
        set_active_session(span, state)

    def ensure(
        self,
        key: str,
        factory: Callable[[], tuple[Span, S] | None],
    ) -> S | None:
        """Return existing session (rebinding active) or create via ``factory``.

        ``factory`` returns ``(span, state)`` or ``None`` when it cannot open
        (e.g. no tracer).
        """
        existing = self._sessions.get(key)
        if existing is not None:
            span, state = existing
            set_active_session(span, state)
            return state
        created = factory()
        if created is None:
            return None
        span, state = created
        self.put(key, span, state)
        return state

    def pop(self, key: str) -> tuple[Span, S] | None:
        return self._sessions.pop(key, None)

    def close(
        self,
        key: str,
        *,
        closer: Callable[[Span, S], None],
        clear_active: bool = True,
    ) -> bool:
        """Pop ``key`` and run ``closer(session_span, state)``.

        Returns True when a session was closed.
        """
        pair = self._sessions.pop(key, None)
        if pair is None:
            return False
        session_span, state = pair
        closer(session_span, state)
        if clear_active:
            active = get_active_session()
            if active is state:
                clear_active_session()
        return True

    def end_and_clear(self, session_span: Span, state: S) -> None:
        """End the session span OK and clear active when it matches ``state``."""
        end_session_span_ok(session_span)
        active = get_active_session()
        if active is state:
            clear_active_session()

    def flush_all(self, closer: Callable[[str], None]) -> None:
        for key in list(self._sessions):
            closer(key)

    def ensure_atexit(self, flush_all: Callable[[], None]) -> None:
        if self._atexit_registered:
            return
        atexit.register(flush_all)
        self._atexit_registered = True
