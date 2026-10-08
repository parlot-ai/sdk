"""Per-session mutable state for LiveKit GenAI span enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from opentelemetry.util.types import AttributeValue

from parlot.core.session import SessionState as _BaseSessionState
from parlot.core.topology import SessionTopology


@dataclass
class _LiveKitSessionState(_BaseSessionState):
    agent_chain: list[str] = field(default_factory=list)
    worker_agent_name: str = ""
    pending_handoff_end_ns: int = 0
    parlot_session_id: str = ""
    conversation_id: str = ""
    last_turn_trace_id: str = ""
    turn_trace_by_index: dict[int, str] = field(default_factory=dict)
    turn_root_span_by_index: dict[int, str] = field(default_factory=dict)
    open_agent_turn_index: Optional[int] = None
    amd: str = ""
    recording_anchor_wall_ms: Optional[int] = None
    languages_seen: set[str] = field(default_factory=set)
    last_user_turn_language: str = ""
    last_agent_turn_language: str = ""
    user_id: str = ""
    pending_tts_ttfb_s: Optional[float] = None
    committed_item_ids: set[str] = field(default_factory=set)
    committed_handoff_ids: set[str] = field(default_factory=set)
    pending_user_speaker_id: str = ""
    pending_user_language: str = ""
    active_speech_id: str = ""
    last_user_input_modality: str = ""
    usage_from_events: bool = False
    metrics_recorded_turns: set[int] = field(default_factory=set)
    pending_close_error: str = ""
    user_text_by_turn: dict[int, str] = field(default_factory=dict)
    agent_text_by_turn: dict[int, str] = field(default_factory=dict)
    last_user_turn_index: int = 0
    tool_execution_ns_queue: list[int] = field(default_factory=list)
    pending_interrupt_media_end_ms: int = 0
    pending_interrupt_speech_end_wall_ms: int = 0
    # Wall-clock ms when the last committed agent turn stopped speaking.
    # Used to clamp LiveKit user started_speaking_at that can open on an early
    # voice-activity-detection (VAD) start of speech before the agent greeting
    # finishes (that first start-of-speech timestamp then spans the greeting).
    last_agent_speech_end_wall_ms: int = 0
    # Attrs observed on native user_turn/agent_turn to stamp onto parlot.turn
    pending_turn_pipeline_attrs: dict[int, dict[str, AttributeValue]] = field(
        default_factory=dict
    )
    topology: SessionTopology = field(default_factory=SessionTopology)
