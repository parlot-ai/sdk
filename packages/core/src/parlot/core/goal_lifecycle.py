"""Goal lifecycle schema for streaming session-close evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GoalOutcome = Literal["open", "completed", "abandoned", "failed"]
GoalLifecycleEventType = Literal["opened", "completed", "abandoned", "failed"]


def fallback_goal_summary(label: str, evidence: str = "") -> str:
    trimmed_label = label.strip() or "Customer goal"
    trimmed_evidence = evidence.strip()
    if trimmed_evidence:
        return f"{trimmed_label}. Evidence: {trimmed_evidence}"
    return trimmed_label


@dataclass
class ActiveGoal:
    goal_id: str
    label: str
    goal_summary: str
    opened_turn: int
    evidence: str = ""
    opened_segment_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "label": self.label,
            "goal_summary": self.goal_summary,
            "opened_turn": self.opened_turn,
            "evidence": self.evidence,
            "opened_segment_index": self.opened_segment_index,
        }


@dataclass
class GoalEvalState:
    active_goals: list[ActiveGoal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"active_goals": [g.to_dict() for g in self.active_goals]}


@dataclass
class GoalLifecycleDelta:
    goal_id: str
    label: str
    turn_index: int
    evidence: str = ""
    goal_summary: str = ""


@dataclass
class GoalLifecycleChunkResult:
    goal_opened: list[GoalLifecycleDelta] = field(default_factory=list)
    goal_completed: list[GoalLifecycleDelta] = field(default_factory=list)
    goal_abandoned: list[GoalLifecycleDelta] = field(default_factory=list)
    goal_failed: list[GoalLifecycleDelta] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_opened": [d.__dict__ for d in self.goal_opened],
            "goal_completed": [d.__dict__ for d in self.goal_completed],
            "goal_abandoned": [d.__dict__ for d in self.goal_abandoned],
            "goal_failed": [d.__dict__ for d in self.goal_failed],
        }


@dataclass
class GoalLifecycleEvent:
    goal_id: str
    event_type: GoalLifecycleEventType
    turn_index: int
    goal_summary: str
    label: str
    evidence: str = ""
    segment_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "event_type": self.event_type,
            "turn_index": self.turn_index,
            "goal_summary": self.goal_summary,
            "label": self.label,
            "evidence": self.evidence,
            "segment_index": self.segment_index,
        }


@dataclass
class GoalLifecycleRow:
    goal_id: str
    label: str
    goal_summary: str
    opened_turn: int
    closed_turn: int | None
    outcome: GoalOutcome
    evidence_turns: list[int] = field(default_factory=list)
    opened_segment_index: int = 0
    closed_segment_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "label": self.label,
            "goal_summary": self.goal_summary,
            "opened_turn": self.opened_turn,
            "closed_turn": self.closed_turn,
            "outcome": self.outcome,
            "evidence_turns": self.evidence_turns,
            "opened_segment_index": self.opened_segment_index,
            "closed_segment_index": self.closed_segment_index,
        }
