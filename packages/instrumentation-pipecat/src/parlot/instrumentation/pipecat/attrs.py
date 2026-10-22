"""Pipecat-native attribute keys (never exported on the wire)."""

from __future__ import annotations

# Observed on Pipecat OTEL spans (TurnTraceObserver / service decorators).
ATTR_PIPECAT_CONVERSATION_ID = "conversation.id"
ATTR_PIPECAT_CONVERSATION_TYPE = "conversation.type"
ATTR_PIPECAT_TURN_NUMBER = "turn.number"
ATTR_PIPECAT_TURN_DURATION = "turn.duration_seconds"
ATTR_PIPECAT_TURN_INTERRUPTED = "turn.was_interrupted"
ATTR_PIPECAT_TURN_USER_BOT_LATENCY = "turn.user_bot_latency_seconds"
ATTR_PIPECAT_TRANSCRIPT = "transcript"
ATTR_PIPECAT_TEXT = "text"
ATTR_PIPECAT_METRICS_TTFB = "metrics.ttfb"
ATTR_PIPECAT_METRICS_CHAR_COUNT = "metrics.character_count"

PIPECAT_FRAMEWORK = "pipecat"
