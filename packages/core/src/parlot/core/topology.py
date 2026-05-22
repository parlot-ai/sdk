"""Per-session agent/tool topology and intent segment accumulator (framework-agnostic)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .intent import derive_intent

_MAX_EDGES = 500
_MAX_JSON_CHARS = 64_000
_INSTRUCTIONS_PREVIEW = 2000
_ARGUMENTS_PREVIEW = 512


@dataclass
class AgentNode:
    id: str
    role: str = "task"
    framework: str = ""


@dataclass
class ToolNode:
    id: str
    name: str = ""
    provider: str = ""
    tool_set: str = ""


@dataclass
class IntentSegmentRecord:
    agent_id: str
    intent_key: str
    intent_label: str
    from_turn: int
    handoff_index: int  # 0 = bootstrap; 1+ = handoff-opened
    to_turn: Optional[int] = None
    instructions_excerpt: str = ""
    source: str = "heuristic"


@dataclass
class EdgeEvent:
    from_agent: str
    to: str
    to_kind: str  # "agent" | "tool"
    latency_ms: float = 0.0
    error: bool = False
    turn_index: int = 0
    arguments: str = ""


@dataclass
class SessionTopology:
    """Runtime autodiscovery of agents, tools, edges, and intent segments for one session."""

    default_framework: str = ""
    agents_seen: dict[str, AgentNode] = field(default_factory=dict)
    tools_seen: dict[str, ToolNode] = field(default_factory=dict)
    edges: list[EdgeEvent] = field(default_factory=list)
    prompts_by_agent: dict[str, str] = field(default_factory=dict)
    intent_by_agent: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    intent_segments: list[IntentSegmentRecord] = field(default_factory=list)
    active_segment: Optional[IntentSegmentRecord] = None
    pending_segment_from_turn: Optional[int] = None
    first_agent_label: str = ""
    orchestrator_label: str = ""

    def upsert_agent(
        self,
        agent_id: str,
        *,
        role: Optional[str] = None,
        framework: Optional[str] = None,
    ) -> None:
        aid = agent_id.strip()
        if not aid:
            return
        if not self.first_agent_label:
            self.first_agent_label = aid
        fw = framework if framework is not None else self.default_framework
        node = self.agents_seen.get(aid)
        if node is None:
            resolved_role = role or (
                "orchestrator"
                if aid == self.first_agent_label and not self.orchestrator_label
                else "task"
            )
            if resolved_role == "orchestrator":
                self.orchestrator_label = aid
            self.agents_seen[aid] = AgentNode(id=aid, role=resolved_role, framework=fw)
        elif role and node.role == "task":
            node.role = role
            if fw and not node.framework:
                node.framework = fw

    def upsert_tool(
        self,
        tool_id: str,
        *,
        name: str = "",
        provider: str = "",
        tool_set: str = "",
    ) -> None:
        tid = tool_id.strip()
        if not tid:
            return
        node = self.tools_seen.get(tid)
        if node is None:
            self.tools_seen[tid] = ToolNode(
                id=tid,
                name=name or tid,
                provider=provider,
                tool_set=tool_set,
            )
        else:
            if name:
                node.name = name
            if provider:
                node.provider = provider
            if tool_set:
                node.tool_set = tool_set

    def append_edge(
        self,
        from_agent: str,
        to: str,
        to_kind: str,
        *,
        latency_ms: float = 0.0,
        error: bool = False,
        turn_index: int = 0,
        arguments: str = "",
    ) -> None:
        if len(self.edges) >= _MAX_EDGES:
            return
        src = from_agent.strip()
        dst = to.strip()
        if not src or not dst:
            return
        self.edges.append(
            EdgeEvent(
                from_agent=src,
                to=dst,
                to_kind=to_kind,
                latency_ms=latency_ms,
                error=error,
                turn_index=turn_index,
                arguments=_truncate(arguments, _ARGUMENTS_PREVIEW),
            )
        )

    def record_instructions(self, agent_id: str, text: str) -> None:
        aid = agent_id.strip()
        if not aid or not text:
            return
        excerpt = _truncate(text, _INSTRUCTIONS_PREVIEW)
        prev = self.prompts_by_agent.get(aid, "")
        if len(excerpt) >= len(prev):
            self.prompts_by_agent[aid] = excerpt
        self._sync_agent_intent_summary(aid)
        self.refresh_open_segment_instructions(aid)

    def _sync_agent_intent_summary(self, agent_id: str) -> None:
        instructions = self.prompts_by_agent.get(agent_id, "")
        self.intent_by_agent[agent_id] = derive_intent(agent_id, instructions)

    def _new_segment(
        self,
        agent_id: str,
        *,
        from_turn: int,
        handoff_index: int,
    ) -> IntentSegmentRecord:
        instructions = self.prompts_by_agent.get(agent_id, "")
        intent_key, intent_label, excerpt = derive_intent(agent_id, instructions)
        self._sync_agent_intent_summary(agent_id)
        return IntentSegmentRecord(
            agent_id=agent_id,
            intent_key=intent_key,
            intent_label=intent_label,
            from_turn=from_turn,
            handoff_index=handoff_index,
            instructions_excerpt=excerpt,
        )

    def open_bootstrap_segment(self, agent_id: str, from_turn: int) -> None:
        """First conversational turn — handoff_index 0."""
        if self.active_segment is not None:
            return
        aid = agent_id.strip() or "unknown"
        self.upsert_agent(aid)
        self.active_segment = self._new_segment(
            aid, from_turn=from_turn, handoff_index=0
        )

    def close_active_segment(self, to_turn: int) -> None:
        if self.active_segment is None:
            return
        seg = self.active_segment
        seg.to_turn = max(0, to_turn)
        self.intent_segments.append(seg)
        self.active_segment = None

    def open_segment_after_handoff(
        self, agent_id: str, handoff_index: int, turn_count: int
    ) -> None:
        """Close outgoing segment; open incoming with from_turn applied on next turn emit."""
        self.close_active_segment(turn_count)
        aid = agent_id.strip()
        if not aid:
            return
        self.upsert_agent(aid)
        self.pending_segment_from_turn = max(1, turn_count + 1)
        self.active_segment = self._new_segment(
            aid,
            from_turn=self.pending_segment_from_turn,
            handoff_index=handoff_index,
        )

    def apply_pending_from_turn_on_emit(self, turn_index: int) -> None:
        """Pin from_turn on the active segment when the first post-handoff turn emits."""
        if self.active_segment is None:
            return
        if self.pending_segment_from_turn is not None:
            self.active_segment.from_turn = self.pending_segment_from_turn
            self.pending_segment_from_turn = None
        elif self.active_segment.from_turn <= 0:
            self.active_segment.from_turn = turn_index

    def refresh_open_segment_instructions(self, agent_id: str) -> None:
        """Update open segment label in place; prior turn snapshots stay unchanged."""
        if self.active_segment is None:
            return
        if self.active_segment.agent_id != agent_id.strip():
            return
        instructions = self.prompts_by_agent.get(agent_id, "")
        intent_key, intent_label, excerpt = derive_intent(agent_id, instructions)
        self.active_segment.intent_key = intent_key
        self.active_segment.intent_label = intent_label
        self.active_segment.instructions_excerpt = excerpt
        self._sync_agent_intent_summary(agent_id)

    def active_intent_snapshot(self) -> tuple[str, str, str]:
        """(intent_label, intent_key, active_agent_id) for turn stamping."""
        if self.active_segment is None:
            if self.first_agent_label:
                key, label, _ = derive_intent(
                    self.first_agent_label,
                    self.prompts_by_agent.get(self.first_agent_label, ""),
                )
                return label, key, self.first_agent_label
            return "Unknown", "unknown", "unknown"
        return (
            self.active_segment.intent_label,
            self.active_segment.intent_key,
            self.active_segment.agent_id,
        )

    def finalize_intent_sequence(self, final_turn: int) -> None:
        if self.active_segment is not None:
            self.close_active_segment(final_turn)

    def intent_sequence_json(self) -> str:
        payload = [
            {
                "segment_index": idx,
                "agent_id": s.agent_id,
                "intent_key": s.intent_key,
                "intent_label": s.intent_label,
                "from_turn": s.from_turn,
                **({"to_turn": s.to_turn} if s.to_turn is not None else {}),
                "handoff_index": s.handoff_index,
                **(
                    {"instructions_excerpt": s.instructions_excerpt}
                    if s.instructions_excerpt
                    else {}
                ),
                "source": s.source,
            }
            for idx, s in enumerate(self.intent_segments)
        ]
        return _json_dumps_cap(payload)

    def orchestrator_instructions(self) -> str:
        if self.orchestrator_label:
            text = self.prompts_by_agent.get(self.orchestrator_label, "")
            if text:
                return text
        if self.first_agent_label:
            text = self.prompts_by_agent.get(self.first_agent_label, "")
            if text:
                return text
        if self.prompts_by_agent:
            return max(self.prompts_by_agent.values(), key=len)
        return ""

    def agents_json(self) -> str:
        payload = []
        for n in self.agents_seen.values():
            entry: dict[str, Any] = {
                "id": n.id,
                "role": n.role,
            }
            if n.framework:
                entry["framework"] = n.framework
            summary = self.intent_by_agent.get(n.id)
            if summary:
                key, label, excerpt = summary
                entry["intent_key"] = key
                entry["intent_label"] = label
                if excerpt:
                    entry["instructions_excerpt"] = excerpt
            payload.append(entry)
        return _json_dumps_cap(payload)

    def tools_json(self) -> str:
        payload = [
            {
                "id": n.id,
                "name": n.name,
                **({"provider": n.provider} if n.provider else {}),
                **({"tool_set": n.tool_set} if n.tool_set else {}),
            }
            for n in self.tools_seen.values()
        ]
        return _json_dumps_cap(payload)

    def edges_json(self) -> str:
        payload = [
            {
                "from": e.from_agent,
                "to": e.to,
                "to_kind": e.to_kind,
                "latency_ms": e.latency_ms,
                "error": e.error,
                "turn_index": e.turn_index,
                **({"arguments": e.arguments} if e.arguments else {}),
            }
            for e in self.edges
        ]
        return _json_dumps_cap(payload)


def _truncate(text: str, limit: int) -> str:
    s = str(text)
    if len(s) <= limit:
        return s
    return s[: limit - 3] + "..."


def _json_dumps_cap(payload: Any) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(raw) <= _MAX_JSON_CHARS:
        return raw
    return raw[: _MAX_JSON_CHARS - 3] + "..."
