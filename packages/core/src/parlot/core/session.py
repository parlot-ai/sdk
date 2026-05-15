"""Base session state accumulator shared across all instrumentation packages."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionState:
    """
    Per-trace accumulator for cross-span aggregates.

    Framework-specific instrumentation packages subclass this to add their own
    fields (e.g. LiveKit adds agent_chain, pending_handoff_end_ns).
    """

    session_id: str = ""
    room_name: str = ""
    room_sid: str = ""
    agent_label: str = ""

    turn_count: int = 0
    tool_call_count: int = 0
    handoff_count: int = 0

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
