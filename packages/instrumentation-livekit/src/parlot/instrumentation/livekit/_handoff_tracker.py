"""Handoff / agent-transfer tracking for LiveKit GenAI enrichment."""

from __future__ import annotations

import time
from collections.abc import Callable

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_LATENCY_MS,
    ATTR_AGENT_TRANSFER_SEQUENCE,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_GEN_AI_TOOL_IS_HANDOFF,
    ATTR_TURN_INDEX,
)
from ._agent_identity import append_agent_chain_step
from ._session import get_job_bootstrap
from ._session_state import _LiveKitSessionState
from ._span_util import extract_new_agent

SetAttrFn = Callable[[ReadableSpan, str, AttributeValue], None]
StampAgentIdentityFn = Callable[..., None]


class HandoffTracker:
    """Owns handoff bookkeeping, span enrichment, and transfer-latency stamping."""

    def __init__(
        self,
        *,
        set_attr: SetAttrFn,
        handoff_tools: set[str],
    ) -> None:
        self._set = set_attr
        self._handoff_tools = handoff_tools

    def mark_handoff_item_committed(self, item_id: str) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        bootstrap.state.committed_handoff_ids.add(item_id)

    def committed_handoff_item_ids(self) -> set[str]:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return set()
        return bootstrap.state.committed_handoff_ids

    def record_handoff_from_event(
        self, *, from_agent: str = "", to_agent: str = ""
    ) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        state.handoff_count += 1
        if to_agent:
            state.agent_label = str(to_agent)
            append_agent_chain_step(state, to_agent)
            turn_index = state.turn_count or state.open_agent_turn_index or 0
            state.topology.open_segment_after_handoff(
                str(to_agent),
                turn_index=int(turn_index),
                from_agent=str(from_agent),
            )

    def enrich_handoff(
        self,
        span: ReadableSpan,
        state: _LiveKitSessionState,
        *,
        stamp_agent_identity: StampAgentIdentityFn,
        turn_source: str,
    ) -> None:
        attrs = span.attributes or {}

        source = attrs.get(ATTR_AGENT_TRANSFER_FROM)
        target = attrs.get(ATTR_AGENT_TRANSFER_TO)
        if target is not None:
            stamp_agent_identity(span, state, attrs, label_override=str(target))
            target_str = str(target)
            state.agent_label = target_str
            append_agent_chain_step(state, target_str)
            raw_turn = attrs.get(ATTR_TURN_INDEX)
            if isinstance(raw_turn, (int, float, str)) and raw_turn:
                try:
                    turn_index = int(raw_turn)
                except (ValueError, TypeError):
                    turn_index = int(state.turn_count or 0)
            else:
                turn_index = int(state.turn_count or 0)
            state.topology.open_segment_after_handoff(
                target_str,
                turn_index=turn_index,
                from_agent=str(source or ""),
            )
        else:
            stamp_agent_identity(span, state, attrs)

        if source is not None or target is not None:
            if turn_source != "events":
                state.handoff_count += 1
                self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)
            elif state.handoff_count:
                self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)

        state.pending_handoff_end_ns = span.end_time or time.time_ns()

    def stamp_transfer_latency_if_pending(
        self, span: ReadableSpan, state: _LiveKitSessionState
    ) -> None:
        if state.pending_handoff_end_ns and span.start_time:
            gap_ms = (span.start_time - state.pending_handoff_end_ns) / 1_000_000
            if 0 < gap_ms < 30_000:
                self._set(span, ATTR_AGENT_TRANSFER_LATENCY_MS, round(gap_ms, 2))
            state.pending_handoff_end_ns = 0

    def apply_function_tool_handoff(
        self,
        span: ReadableSpan,
        state: _LiveKitSessionState,
        *,
        tool_name: str,
        tool_output: str,
    ) -> bool:
        """Apply handoff side effects for a function_tool span. Returns is_handoff."""
        is_handoff = tool_name in self._handoff_tools or "AgentHandoff" in tool_output
        new_agent = extract_new_agent(tool_output) if is_handoff else ""

        if is_handoff:
            state.handoff_count += 1
            self._set(span, ATTR_GEN_AI_TOOL_IS_HANDOFF, True)
            self._set(span, ATTR_AGENT_TRANSFER_SEQUENCE, state.handoff_count)

            if new_agent:
                self._set(span, ATTR_AGENT_TRANSFER_TO, new_agent)
                state.agent_label = new_agent
                append_agent_chain_step(state, new_agent)

            state.pending_handoff_end_ns = span.end_time or time.time_ns()

        return is_handoff
