"""Explicit Parlot SDK instance state (runtime + collectors)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from parlot.core.runtime import ParlotRuntimeContext
from parlot.core.session_logs import SessionLogsCollector


@dataclass
class ParlotContext:
    """Owns bootstrap runtime and process-local collectors for one SDK instance."""

    runtime: Optional[ParlotRuntimeContext] = None
    session_logs: SessionLogsCollector = field(default_factory=SessionLogsCollector)

    def __post_init__(self) -> None:
        self.session_logs.bind_context(self)

    def shutdown(self) -> None:
        self.session_logs.shutdown()
        self.runtime = None
