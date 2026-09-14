"""Runtime session topology: intent segments + per-agent instructions at session close."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from parlot.core.attrs import (
    ATTR_SESSION_AGENT_CHAIN,
    ATTR_SESSION_AGENT_CHAIN_TRUNCATED,
    ATTR_SESSION_INTENT_SEQUENCE,
    ATTR_SESSION_INTENT_SEQUENCE_TRUNCATED,
    ATTR_SESSION_TOPOLOGY_AGENTS,
    ATTR_SESSION_TOPOLOGY_AGENTS_TRUNCATED,
    ATTR_SESSION_TOPOLOGY_BOOTSTRAP_INSTRUCTIONS,
)
from parlot.core.intent import derive_intent

INSTRUCTIONS_PREVIEW = 2000
MAX_JSON_CHARS = 64_000

# Independent retention windows — must not be assumed to match after both caps fire.
# Under long ping-pong handoffs, agent_chain may keep the last 64 steps while
# intent_segments keeps the last 128 closed segments.
MAX_AGENT_CHAIN_STEPS = 64
MAX_INTENT_SEGMENTS = 128


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _json_dumps_cap(payload: list[dict[str, Any]]) -> tuple[str, bool]:
    """Serialize ``payload`` under ``MAX_JSON_CHARS``, keeping the newest items.

    Returns ``(json_str, truncated)``. Drops from the front when oversized.
    """
    if not payload:
        return "[]", False
    full = json.dumps(payload, separators=(",", ":"))
    if len(full) <= MAX_JSON_CHARS:
        return full, False

    # Binary search largest k such that payload[-k:] fits.
    lo, hi = 0, len(payload)
    best = "[]"
    while lo < hi:
        mid = (lo + hi + 1) // 2
        raw = json.dumps(payload[-mid:], separators=(",", ":"))
        if len(raw) <= MAX_JSON_CHARS:
            best = raw
            lo = mid
        else:
            hi = mid - 1
    return best, True


def trim_agent_chain(chain: list[str], *, max_steps: int = MAX_AGENT_CHAIN_STEPS) -> None:
    """Keep first (canonical) step + most recent ``max_steps - 1`` steps in place."""
    if max_steps < 1 or len(chain) <= max_steps:
        return
    if max_steps == 1:
        chain[:] = [chain[0]]
        return
    chain[:] = [chain[0]] + chain[-(max_steps - 1) :]


def _agent_id_of(seg: _MutableSegment | dict[str, Any]) -> str:
    if isinstance(seg, _MutableSegment):
        return seg.agent_id
    return str(seg.get("agent_id", ""))


def _merge_same_agent_into(
    prev: _MutableSegment | dict[str, Any],
    nxt: _MutableSegment | dict[str, Any],
) -> bool:
    """If same agent_id, extend prev.to_turn and copy missing instructions_excerpt."""
    if _agent_id_of(prev) != _agent_id_of(nxt):
        return False
    if isinstance(prev, _MutableSegment) and isinstance(nxt, _MutableSegment):
        prev.to_turn = nxt.to_turn if nxt.to_turn is not None else prev.to_turn
        if nxt.instructions_excerpt and not prev.instructions_excerpt:
            prev.instructions_excerpt = nxt.instructions_excerpt
        return True
    if isinstance(prev, dict) and isinstance(nxt, dict):
        prev["to_turn"] = nxt.get("to_turn", prev.get("to_turn"))
        if nxt.get("instructions_excerpt") and not prev.get("instructions_excerpt"):
            prev["instructions_excerpt"] = nxt["instructions_excerpt"]
        return True
    return False


@dataclass
class _MutableSegment:
    segment_index: int
    agent_id: str
    intent_key: str
    intent_label: str
    from_turn: int
    handoff_index: int
    source: str = "heuristic"
    instructions_excerpt: str = ""
    to_turn: int | None = None


@dataclass
class SessionTopology:
    """
    Accumulates intent segments and agent instructions during a live session.

    Framework adapters call ``record_instructions`` / ``open_segment_after_handoff``
    during the session and ``stamp_session_span`` at close.
    """

    prompts_by_agent: dict[str, str] = field(default_factory=dict)
    intent_by_agent: dict[str, dict[str, str]] = field(default_factory=dict)
    # Expected to be a small fixed agent roster (not session-/user-suffixed ids).
    agents_seen: dict[str, dict[str, Any]] = field(default_factory=dict)
    intent_segments: list[_MutableSegment] = field(default_factory=list)
    active_segment: _MutableSegment | None = None
    pending_segment_from_turn: int | None = None
    first_agent_label: str = ""
    agent_chain: list[str] = field(default_factory=list)
    handoff_count: int = 0
    _handoff_keys: set[str] = field(default_factory=set)
    _handoff_keys_turn: int | None = None

    def upsert_agent(self, agent_id: str) -> None:
        aid = agent_id.strip()
        if not aid:
            return
        if not self.first_agent_label:
            self.first_agent_label = aid
        if aid not in self.agents_seen:
            self.agents_seen[aid] = {"id": aid, "role": "agent"}

    def record_instructions(self, agent_id: str, text: str) -> None:
        # Keep the longer excerpt so a later shorter capture does not shrink the preview.
        aid = agent_id.strip()
        if not aid or not text.strip():
            return
        excerpt = _truncate(text.strip(), INSTRUCTIONS_PREVIEW)
        prev = self.prompts_by_agent.get(aid, "")
        if len(excerpt) >= len(prev):
            self.prompts_by_agent[aid] = excerpt
        self._sync_agent_intent_summary(aid)
        self._refresh_open_segment_instructions(aid)

    def push_agent_chain(self, agent_id: str) -> None:
        aid = agent_id.strip()
        if not aid:
            return
        if not self.agent_chain or self.agent_chain[-1] != aid:
            self.agent_chain.append(aid)
            trim_agent_chain(self.agent_chain)

    def open_bootstrap_segment(self, agent_id: str, from_turn: int) -> None:
        if self.active_segment is not None:
            return
        aid = agent_id.strip() or "unknown"
        self.upsert_agent(aid)
        self.active_segment = self._new_segment(aid, from_turn, 0)

    def open_segment_after_handoff(
        self,
        agent_id: str,
        *,
        handoff_index: int | None = None,
        turn_index: int,
        from_agent: str = "",
    ) -> None:
        aid = agent_id.strip()
        if not aid:
            return
        if self._handoff_keys_turn != turn_index:
            self._handoff_keys.clear()
            self._handoff_keys_turn = turn_index
        dedupe_key = f"{from_agent.strip()}->{aid}@{turn_index}"
        if dedupe_key in self._handoff_keys:
            return
        self._handoff_keys.add(dedupe_key)

        self.close_active_segment(turn_index)
        self.upsert_agent(aid)
        self.handoff_count += 1
        effective_handoff = handoff_index if handoff_index is not None else self.handoff_count
        if not self.intent_segments and self.active_segment is None:
            effective_handoff = 0
        self.pending_segment_from_turn = max(1, turn_index + 1)
        self.active_segment = self._new_segment(
            aid,
            self.pending_segment_from_turn,
            effective_handoff,
        )

    def close_active_segment(self, to_turn: int) -> None:
        if self.active_segment is None:
            return
        self.active_segment.to_turn = max(0, to_turn)
        closed = self.active_segment
        self.active_segment = None
        if self.intent_segments and _merge_same_agent_into(self.intent_segments[-1], closed):
            self._trim_closed_segments()
            return
        self.intent_segments.append(closed)
        self._trim_closed_segments()

    def _trim_closed_segments(self) -> None:
        """Drop oldest closed segments only; never touches ``active_segment``."""
        overflow = len(self.intent_segments) - MAX_INTENT_SEGMENTS
        if overflow > 0:
            del self.intent_segments[:overflow]

    def apply_pending_from_turn_on_emit(self, turn_index: int) -> None:
        if self.active_segment is None:
            return
        if self.pending_segment_from_turn is not None:
            self.active_segment.from_turn = self.pending_segment_from_turn
            self.pending_segment_from_turn = None
        elif self.active_segment.from_turn <= 0:
            self.active_segment.from_turn = turn_index

    def finalize_intent_sequence(self, final_turn: int) -> list[dict[str, Any]]:
        if self.active_segment is not None:
            self.close_active_segment(final_turn)
        return self._collapse_segments(
            [
                {
                    "segment_index": idx,
                    "agent_id": seg.agent_id,
                    "intent_key": seg.intent_key,
                    "intent_label": seg.intent_label,
                    "from_turn": seg.from_turn,
                    "handoff_index": seg.handoff_index,
                    "source": seg.source,
                    **(
                        {"to_turn": seg.to_turn}
                        if seg.to_turn is not None
                        else {}
                    ),
                    **(
                        {"instructions_excerpt": seg.instructions_excerpt}
                        if seg.instructions_excerpt
                        else {}
                    ),
                }
                for idx, seg in enumerate(self.intent_segments)
            ]
        )

    def bootstrap_instructions(self) -> str:
        if self.first_agent_label:
            text = self.prompts_by_agent.get(self.first_agent_label, "")
            if text:
                return text
        if self.prompts_by_agent:
            return max(self.prompts_by_agent.values(), key=len)
        return ""

    def agents_json(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for node in self.agents_seen.values():
            summary = self.intent_by_agent.get(node["id"], {})
            entry = dict(node)
            if summary:
                entry["intent_key"] = summary.get("intent_key", node["id"])
                entry["intent_label"] = summary.get("intent_label", node["id"])
                excerpt = summary.get("instructions_excerpt", "")
                if excerpt:
                    entry["instructions_excerpt"] = excerpt
            out.append(entry)
        return out

    def stamp_session_span(self, span: Any, *, final_turn: int) -> None:
        """Write topology attrs on the live ``parlot.session`` span."""
        if span is None or not hasattr(span, "set_attribute"):
            return
        sequence = self.finalize_intent_sequence(final_turn)
        agents = self.agents_json()
        bootstrap = self.bootstrap_instructions()
        if agents:
            agents_json, agents_truncated = _json_dumps_cap(agents)
            span.set_attribute(ATTR_SESSION_TOPOLOGY_AGENTS, agents_json)
            if agents_truncated:
                span.set_attribute(ATTR_SESSION_TOPOLOGY_AGENTS_TRUNCATED, True)
        if bootstrap:
            span.set_attribute(ATTR_SESSION_TOPOLOGY_BOOTSTRAP_INSTRUCTIONS, bootstrap)
        if sequence:
            seq_json, seq_truncated = _json_dumps_cap(sequence)
            span.set_attribute(ATTR_SESSION_INTENT_SEQUENCE, seq_json)
            if seq_truncated:
                span.set_attribute(ATTR_SESSION_INTENT_SEQUENCE_TRUNCATED, True)
        if self.agent_chain:
            chain = " → ".join(self.agent_chain)
            span.set_attribute(ATTR_SESSION_AGENT_CHAIN, _truncate(chain, MAX_JSON_CHARS))
            if len(chain) > MAX_JSON_CHARS:
                span.set_attribute(ATTR_SESSION_AGENT_CHAIN_TRUNCATED, True)

    def _new_segment(self, agent_id: str, from_turn: int, handoff_index: int) -> _MutableSegment:
        instructions = self.prompts_by_agent.get(agent_id, "")
        derived = derive_intent(agent_id, instructions)
        self._sync_agent_intent_summary(agent_id)
        return _MutableSegment(
            segment_index=0,
            agent_id=agent_id,
            intent_key=derived["intent_key"],
            intent_label=derived["intent_label"],
            from_turn=from_turn,
            handoff_index=handoff_index,
            instructions_excerpt=derived.get("instructions_excerpt", ""),
        )

    def _sync_agent_intent_summary(self, agent_id: str) -> None:
        instructions = self.prompts_by_agent.get(agent_id, "")
        derived = derive_intent(agent_id, instructions)
        self.intent_by_agent[agent_id] = derived
        node = self.agents_seen.get(agent_id)
        if node is not None:
            node["intent_key"] = derived["intent_key"]
            node["intent_label"] = derived["intent_label"]
            if derived.get("instructions_excerpt"):
                node["instructions_excerpt"] = derived["instructions_excerpt"]

    def _refresh_open_segment_instructions(self, agent_id: str) -> None:
        if self.active_segment is None or self.active_segment.agent_id != agent_id.strip():
            return
        instructions = self.prompts_by_agent.get(agent_id, "")
        derived = derive_intent(agent_id, instructions)
        self.active_segment.intent_key = derived["intent_key"]
        self.active_segment.intent_label = derived["intent_label"]
        self.active_segment.instructions_excerpt = derived.get("instructions_excerpt", "")
        self._sync_agent_intent_summary(agent_id)

    @staticmethod
    def _collapse_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not segments:
            return []
        merged: list[dict[str, Any]] = []
        for seg in segments:
            if not merged:
                merged.append(dict(seg))
                continue
            prev = merged[-1]
            if _merge_same_agent_into(prev, seg):
                continue
            merged.append(dict(seg))
        for idx, seg in enumerate(merged):
            seg["segment_index"] = idx
        return merged
