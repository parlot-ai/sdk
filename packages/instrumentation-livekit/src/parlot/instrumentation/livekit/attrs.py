"""
LiveKit Agents vendor attribute keys (mirrored from livekit-agents telemetry).

Synced with livekit-agents ``telemetry/trace_types.py`` @ 1.5.9.
On LK upgrade, diff trace_types.py and update this file.

Do not add Parlot-invented keys here — use ``parlot.core.attrs`` for
``turn.*``, ``session.*``, ``agent.transfer.*``, etc. Exception recording
(``exception.*``) and cross-cutting session keys are re-exported from core below.
"""

from __future__ import annotations

from parlot.core.attrs import (
    ATTR_EXCEPTION_MESSAGE,
    ATTR_EXCEPTION_TRACE,
    ATTR_EXCEPTION_TYPE,
    ATTR_SESSION_RECORDING_EGRESS_ID,
)

# ---------------------------------------------------------------------------
# Mirrored from livekit-agents telemetry/trace_types.py @ 1.5.9
# ---------------------------------------------------------------------------

ATTR_SPEECH_ID = "lk.speech_id"
ATTR_AGENT_LABEL = "lk.agent_label"
ATTR_START_TIME = "lk.start_time"
ATTR_END_TIME = "lk.end_time"
ATTR_RETRY_COUNT = "lk.retry_count"
ATTR_PROVIDER_REQUEST_IDS = "lk.provider_request_ids"

ATTR_PARTICIPANT_ID = "lk.participant_id"
ATTR_PARTICIPANT_IDENTITY = "lk.participant_identity"
ATTR_PARTICIPANT_KIND = "lk.participant_kind"

ATTR_JOB_ID = "lk.job_id"
ATTR_AGENT_NAME = "lk.agent_name"
ATTR_ROOM_NAME = "lk.room_name"
ATTR_SESSION_OPTIONS = "lk.session_options"

ATTR_AGENT_TURN_ID = "lk.generation_id"
ATTR_AGENT_PARENT_TURN_ID = "lk.parent_generation_id"
ATTR_USER_INPUT = "lk.user_input"
ATTR_INSTRUCTIONS = "lk.instructions"
ATTR_SPEECH_INTERRUPTED = "lk.interrupted"

ATTR_CHAT_CTX = "lk.chat_ctx"
ATTR_FUNCTION_TOOLS = "lk.function_tools"
ATTR_PROVIDER_TOOLS = "lk.provider_tools"
ATTR_TOOL_SETS = "lk.tool_sets"
ATTR_RESPONSE_TEXT = "lk.response.text"
ATTR_RESPONSE_FUNCTION_CALLS = "lk.response.function_calls"
ATTR_RESPONSE_TTFT = "lk.response.ttft"

ATTR_FUNCTION_TOOL_ID = "lk.function_tool.id"
ATTR_FUNCTION_TOOL_NAME = "lk.function_tool.name"
ATTR_FUNCTION_TOOL_ARGS = "lk.function_tool.arguments"
ATTR_FUNCTION_TOOL_IS_ERROR = "lk.function_tool.is_error"
ATTR_FUNCTION_TOOL_OUTPUT = "lk.function_tool.output"

ATTR_TTS_INPUT_TEXT = "lk.input_text"
ATTR_TTS_STREAMING = "lk.tts.streaming"
ATTR_TTS_LABEL = "lk.tts.label"
ATTR_RESPONSE_TTFB = "lk.response.ttfb"

ATTR_EOU_PROBABILITY = "lk.eou.probability"
ATTR_EOU_UNLIKELY_THRESHOLD = "lk.eou.unlikely_threshold"
ATTR_EOU_DELAY = "lk.eou.endpointing_delay"
ATTR_EOU_LANGUAGE = "lk.eou.language"
ATTR_USER_TRANSCRIPT = "lk.user_transcript"
ATTR_TRANSCRIPT_CONFIDENCE = "lk.transcript_confidence"
ATTR_TRANSCRIPTION_DELAY = "lk.transcription_delay"
ATTR_END_OF_TURN_DELAY = "lk.end_of_turn_delay"

ATTR_LLM_METRICS = "lk.llm_metrics"
ATTR_TTS_METRICS = "lk.tts_metrics"
ATTR_REALTIME_MODEL_METRICS = "lk.realtime_model_metrics"

ATTR_E2E_LATENCY = "lk.e2e_latency"

ATTR_GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
ATTR_GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
ATTR_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_GEN_AI_USAGE_INPUT_TEXT_TOKENS = "gen_ai.usage.input_text_tokens"
ATTR_GEN_AI_USAGE_INPUT_AUDIO_TOKENS = "gen_ai.usage.input_audio_tokens"
ATTR_GEN_AI_USAGE_INPUT_CACHED_TOKENS = "gen_ai.usage.input_cached_tokens"
ATTR_GEN_AI_USAGE_OUTPUT_TEXT_TOKENS = "gen_ai.usage.output_text_tokens"
ATTR_GEN_AI_USAGE_OUTPUT_AUDIO_TOKENS = "gen_ai.usage.output_audio_tokens"

EVENT_GEN_AI_SYSTEM_MESSAGE = "gen_ai.system.message"
EVENT_GEN_AI_USER_MESSAGE = "gen_ai.user.message"
EVENT_GEN_AI_ASSISTANT_MESSAGE = "gen_ai.assistant.message"
EVENT_GEN_AI_TOOL_MESSAGE = "gen_ai.tool.message"
EVENT_GEN_AI_CHOICE = "gen_ai.choice"

ATTR_LANGFUSE_COMPLETION_START_TIME = "langfuse.observation.completion_start_time"

ATTR_AMD_CATEGORY = "lk.amd.category"
ATTR_AMD_REASON = "lk.amd.reason"
ATTR_AMD_SPEECH_DURATION = "lk.amd.speech_duration"
ATTR_AMD_DELAY = "lk.amd.delay"
ATTR_AMD_TRANSCRIPT = "lk.amd.transcript"

ATTR_IS_INTERRUPTION = "lk.is_interruption"
ATTR_INTERRUPTION_PROBABILITY = "lk.interruption.probability"
ATTR_INTERRUPTION_TOTAL_DURATION = "lk.interruption.total_duration"
ATTR_INTERRUPTION_PREDICTION_DURATION = "lk.interruption.prediction_duration"
ATTR_INTERRUPTION_DETECTION_DELAY = "lk.interruption.detection_delay"

# Stamped by Parlot platform refs / job context (not in trace_types.py)
ATTR_ROOM_SID = "lk.room.sid"

# participant.diarization_source values (LiveKit Agents instrumentation only)
ATTR_DIAR_SOURCE_VAD = "livekit_vad"
ATTR_DIAR_SOURCE_TEXT_INPUT = "livekit_text_input"
ATTR_DIAR_SOURCE_STT_EVENT = "livekit_stt_event"

# Aliases used by instrumentation-livekit (same strings as above)
ATTR_LK_SPEECH_ID = ATTR_SPEECH_ID
ATTR_LK_AGENT_LABEL = ATTR_AGENT_LABEL
ATTR_LK_JOB_ID = ATTR_JOB_ID
ATTR_LK_AGENT_NAME = ATTR_AGENT_NAME
ATTR_LK_ROOM_NAME = ATTR_ROOM_NAME
ATTR_LK_ROOM_SID = ATTR_ROOM_SID
ATTR_LK_TURN_ID = ATTR_AGENT_TURN_ID
ATTR_LK_PARENT_TURN_ID = ATTR_AGENT_PARENT_TURN_ID
ATTR_LK_USER_INPUT = ATTR_USER_INPUT
ATTR_LK_INSTRUCTIONS = ATTR_INSTRUCTIONS
ATTR_LK_INTERRUPTED = ATTR_SPEECH_INTERRUPTED
ATTR_LK_IS_INTERRUPTION = ATTR_IS_INTERRUPTION
ATTR_LK_CHAT_CTX = ATTR_CHAT_CTX
ATTR_LK_FUNCTION_TOOLS = ATTR_FUNCTION_TOOLS
ATTR_LK_PROVIDER_TOOLS = ATTR_PROVIDER_TOOLS
ATTR_LK_TOOL_SETS = ATTR_TOOL_SETS
ATTR_LK_RESPONSE_TEXT = ATTR_RESPONSE_TEXT
ATTR_LK_RESPONSE_TTFT = ATTR_RESPONSE_TTFT
ATTR_LK_TTS_INPUT_TEXT = ATTR_TTS_INPUT_TEXT
ATTR_LK_RESPONSE_TTFB = ATTR_RESPONSE_TTFB
ATTR_LK_FNC_TOOL_ID = ATTR_FUNCTION_TOOL_ID
ATTR_LK_FNC_TOOL_NAME = ATTR_FUNCTION_TOOL_NAME
ATTR_LK_FNC_TOOL_ARGS = ATTR_FUNCTION_TOOL_ARGS
ATTR_LK_FNC_TOOL_OUTPUT = ATTR_FUNCTION_TOOL_OUTPUT
ATTR_LK_FNC_TOOL_ERROR = ATTR_FUNCTION_TOOL_IS_ERROR
ATTR_LK_USER_TRANSCRIPT = ATTR_USER_TRANSCRIPT
ATTR_LK_E2E_LATENCY = ATTR_E2E_LATENCY

# Unprefixed keys from LK _MetadataSpanProcessor (resolve in processor, not constants)
METADATA_JOB_ID = "job_id"
METADATA_ROOM_ID = "room_id"
