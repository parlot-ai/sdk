"""
Semantic convention attribute name constants for Parlot instrumentation.

TypeScript: ``@parlot/core`` (``packages/core-ts/src/attrs.gen.ts``), generated via
``uv run python scripts/generate_attrs_ts.py``.

LiveKit vendor keys: ``parlot.instrumentation.livekit.attrs`` → ``@parlot/core/livekit``.
OTel-standard keys (e.g. ``exception.*``) live here, not in the LiveKit vendor module.

Three-layer strategy (system-design.md §3.6):
  Layer 1 — gen_ai.*          OTel GenAI SemConv (never deviate)
  Layer 2 — openinference.*   OpenInference semantic model
  Layer 3 — Parlot extensions  agent.*, voice.*, session.*, turn.*, participant.*,
                               conversation.*, platform.ref.*
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Layer 1 — OTel GenAI SemConv (gen_ai.*)
# ---------------------------------------------------------------------------

ATTR_GEN_AI_SYSTEM          = "gen_ai.system"
ATTR_GEN_AI_OP_NAME         = "gen_ai.operation.name"
ATTR_GEN_AI_PROVIDER        = "gen_ai.provider.name"
ATTR_GEN_AI_MODEL           = "gen_ai.request.model"
ATTR_GEN_AI_RESPONSE_MODEL  = "gen_ai.response.model"
ATTR_GEN_AI_IN_TOKENS       = "gen_ai.usage.input_tokens"
ATTR_GEN_AI_OUT_TOKENS      = "gen_ai.usage.output_tokens"
ATTR_GEN_AI_CACHED_TOKENS   = "gen_ai.usage.input_cached_tokens"
ATTR_GEN_AI_AUDIO_IN        = "gen_ai.usage.input_audio_tokens"
ATTR_GEN_AI_AUDIO_OUT       = "gen_ai.usage.output_audio_tokens"
ATTR_GEN_AI_COST_USD        = "gen_ai.usage.cost_usd"
ATTR_GEN_AI_CACHE_HIT_RATE  = "gen_ai.usage.cache_hit_rate"

# OTel GenAI Agent Spans spec (Development status, May 2026)
ATTR_GEN_AI_AGENT_ID        = "gen_ai.agent.id"
ATTR_GEN_AI_AGENT_NAME      = "gen_ai.agent.name"
ATTR_GEN_AI_AGENT_VERSION   = "gen_ai.agent.version"
ATTR_GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"   # maps to parlot conversation_id

# TTS extension (not yet in spec)
ATTR_GEN_AI_TTS_TTFB_S      = "gen_ai.tts.ttfb_s"

# Tool extensions
ATTR_GEN_AI_TOOL_IS_HANDOFF  = "gen_ai.tool.is_handoff"
ATTR_GEN_AI_TOOL_DURATION_MS = "gen_ai.tool.duration_ms"
ATTR_TOOL_INPUT_PAYLOAD        = "tool.input.payload"
ATTR_TOOL_INPUT_PAYLOAD_PREVIEW = "tool.input.payload_preview"
ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW = "tool.output.payload_preview"

# GenAI message events (OTel GenAI events, used for content capture)
EVENT_GEN_AI_USER_MESSAGE       = "gen_ai.user.message"
EVENT_GEN_AI_ASSISTANT_MESSAGE  = "gen_ai.assistant.message"
EVENT_GEN_AI_TOOL_MESSAGE       = "gen_ai.tool.message"

# ---------------------------------------------------------------------------
# Layer 2 — OpenInference
# ---------------------------------------------------------------------------

ATTR_OI_SPAN_KIND = "openinference.span.kind"
# Values: AGENT | CHAIN | TOOL | RETRIEVER | LLM | EMBEDDING | EVAL

# ---------------------------------------------------------------------------
# OTel exception recording (exception.* — all frameworks, not vendor-specific)
# ---------------------------------------------------------------------------

ATTR_EXCEPTION_TYPE     = "exception.type"
ATTR_EXCEPTION_MESSAGE  = "exception.message"
ATTR_EXCEPTION_TRACE    = "exception.stacktrace"

# ---------------------------------------------------------------------------
# Layer 3 — Parlot extensions
# ---------------------------------------------------------------------------

# -- Agent identity (gaps the OTel spec does not cover) --------------------
ATTR_AGENT_ROLE      = "agent.role"       # pipeline/component role: stt | tts | llm | tool | amd | pipeline | handoff | guardrail (not agent id/name)
ATTR_AGENT_STAGE     = "agent.stage"      # lifecycle stage within role: node | request | run | turn | eou | drain | call | transfer | classify
ATTR_AGENT_FRAMEWORK = "agent.framework"  # livekit | crewai | langgraph | adk | custom
ATTR_AGENT_INSTRUCTIONS_EXCERPT = "agent.instructions_excerpt"
ATTR_AGENT_STATIC_INSTRUCTIONS_EXCERPT = "agent.static_instructions_excerpt"
ATTR_AGENT_TOOL_NAMES = "agent.tool.names"  # JSON array of tool name strings
ATTR_AGENT_TOOL_NAME = "agent.tool.name"
ATTR_AGENT_TOOL_IS_ERROR = "agent.tool.is_error"

# -- Agent coordination ----------------------------------------------------
ATTR_AGENT_TRANSFER_FROM    = "agent.transfer.from_agent_id"
ATTR_AGENT_TRANSFER_TO      = "agent.transfer.to_agent_id"
ATTR_AGENT_TRANSFER_REASON  = "agent.transfer.reason"
ATTR_AGENT_TRANSFER_BYTES   = "agent.transfer.context_payload_bytes"
ATTR_AGENT_TRANSFER_SEQUENCE = "agent.transfer.sequence"
ATTR_AGENT_TRANSFER_ITEM_ID = "agent.transfer.item_id"
ATTR_AGENT_TRANSFER_CREATED_AT = "agent.transfer.created_at"
ATTR_AGENT_TRANSFER_LATENCY_MS = "agent.transfer.transition_latency_ms"
ATTR_AGENT_COORD_OVERHEAD   = "agent.coordination.overhead_ms"
ATTR_AGENT_TOOL_CALL_INDEX  = "agent.tool_call.index"
ATTR_AGENT_TOOL_TIMING_CORRECTED = "agent.tool.timing_corrected"

# -- Session ---------------------------------------------------------------
ATTR_SESSION_ID             = "session.id"
ATTR_SESSION_CONVERSATION_ID = "session.conversation_id"
ATTR_SESSION_MODALITY       = "session.modality"         # voice | text | multimodal
ATTR_SESSION_PARTICIPANT_COUNT = "session.participant_count"
ATTR_SESSION_INTENT_LABEL   = "session.intent_label"
ATTR_SESSION_INTENT_SEQUENCE = "session.intent.sequence"
ATTR_SESSION_AMD            = "session.amd"              # human | voicemail | ivr | unavailable | unknown
ATTR_SESSION_TURN_COUNT     = "session.turn_count"
ATTR_SESSION_TOOL_CALL_COUNT = "session.tool_call_count"
ATTR_SESSION_HANDOFF_COUNT  = "session.handoff_count"
ATTR_SESSION_TOTAL_INPUT_TOKENS = "session.total_input_tokens"
ATTR_SESSION_TOTAL_OUTPUT_TOKENS = "session.total_output_tokens"
ATTR_SESSION_TOTAL_COST_USD = "session.total_cost_usd"
ATTR_SESSION_AGENT_ID = "session.agent_id"
ATTR_SESSION_AGENT_FRAMEWORK = "session.agent_framework"
ATTR_SESSION_AGENT_FRAMEWORK_RAW_ID = "session.agent_framework_raw_id"
ATTR_PARLOT_SDK_VERSION = "parlot.sdk.version"

# -- Session custom metadata (public user bag; prefix-passthrough at ingest) --
ATTR_SESSION_METADATA_PREFIX = "session.metadata."

# -- OTLP metric names (Parlot contract; framework adapters map vendor usage here) --
METRIC_USAGE_LLM_INPUT_TOKENS = "usage.llm_input_tokens"
METRIC_USAGE_LLM_OUTPUT_TOKENS = "usage.llm_output_tokens"
METRIC_USAGE_STT_AUDIO_DURATION = "usage.stt_audio_duration"
METRIC_USAGE_TTS_AUDIO_DURATION = "usage.tts_audio_duration"
METRIC_USAGE_TTS_CHARACTERS = "usage.tts_characters"
METRIC_SESSION_TURN_COUNT = "session.turn_count"
METRIC_SESSION_TOTAL_INPUT_TOKENS = "session.total_input_tokens"
METRIC_SESSION_TOTAL_OUTPUT_TOKENS = "session.total_output_tokens"
ATTR_SESSION_AGENT_CHAIN    = "session.agent_chain"
ATTR_SESSION_TOPOLOGY_AGENTS = "session.topology.agents"
ATTR_SESSION_TOPOLOGY_TOOLS  = "session.topology.tools"
ATTR_SESSION_TOPOLOGY_EDGES = "session.topology.edges"
ATTR_SESSION_TOPOLOGY_BOOTSTRAP_INSTRUCTIONS = "session.topology.bootstrap_instructions"
ATTR_SESSION_RECORDING_ANCHOR_WALL_MS = "session.recording.anchor_wall_ms"
ATTR_SESSION_RECORDING_AUDIO_URI = "session.recording.audio_uri"
ATTR_SESSION_RECORDING_EGRESS_ID = "session.recording.egress_id"
ATTR_SESSION_RECORDING_WEBHOOK_ERROR = "session.recording.webhook_error"
ATTR_SESSION_LANGUAGES = "session.languages"
ATTR_SESSION_CLOSE_REASON = "session.close_reason"
ATTR_SESSION_USER_ID = "session.user_id"
ATTR_SESSION_CLOSE_ERROR = "session.close_error"

# -- Framework-agnostic Parlot span names -----------------------------------
SPAN_CONVERSATION_SESSION = "parlot.session"
SPAN_PARLOT_TURN = "parlot.turn"
SPAN_PARLOT_SESSION_CLOSE = "parlot.session.close"
SPAN_AGENT_HANDOFF = "parlot.agent.handoff"

# -- Conversation ----------------------------------------------------------
ATTR_CONVERSATION_ID      = "conversation.id"
ATTR_CONVERSATION_CHANNEL = "conversation.channel"  # voice | webchat | sms | whatsapp

# -- Turn ------------------------------------------------------------------
ATTR_TURN_PREV_TRACE_ID     = "turn.prev_trace_id"
ATTR_TURN_INDEX             = "turn.index"
ATTR_TURN_PARTICIPANT_ID    = "turn.participant_id"
ATTR_TURN_PARTICIPANT_ROLE  = "turn.participant_role"
ATTR_TURN_PARTICIPANT_LABEL = "turn.participant_label"
ATTR_TURN_INPUT_MODALITY    = "turn.input_modality"      # voice | text (user turns)
ATTR_TURN_MEDIA_START_MS    = "turn.media_segment_start_ms"
ATTR_TURN_MEDIA_END_MS      = "turn.media_segment_end_ms"
ATTR_TURN_SPEECH_WALL_START_MS = "turn.speech_wall_start_ms"
ATTR_TURN_SPEECH_WALL_END_MS   = "turn.speech_wall_end_ms"
ATTR_TURN_INTERRUPTED       = "turn.interrupted"
ATTR_TURN_E2E_LATENCY_S     = "turn.e2e_latency_s"
ATTR_TURN_LLM_TTFT_S        = "turn.llm_ttft_s"
ATTR_TURN_TTS_TTFB_S        = "turn.tts_ttfb_s"
ATTR_TURN_TRANSCRIPTION_DELAY_S = "turn.transcription_delay_s"
ATTR_TURN_EOU_DELAY_S       = "turn.eou_delay_s"
ATTR_TURN_LANGUAGE          = "turn.language"
ATTR_TURN_LANGUAGE_SWITCH   = "turn.language_switch"
ATTR_TURN_USER_TEXT         = "turn.user_text"
ATTR_TURN_AGENT_TEXT        = "turn.agent_text"
ATTR_TURN_INTENT_LABEL      = "turn.intent_label"
ATTR_TURN_INTENT_KEY        = "turn.intent_key"
ATTR_TURN_ACTIVE_AGENT_ID   = "turn.active_agent_id"

# -- Participant / Diarization ---------------------------------------------
ATTR_PARTICIPANT_ID           = "participant.id"
ATTR_PARTICIPANT_ROLE         = "participant.role"
ATTR_PARTICIPANT_LABEL        = "participant.label"
ATTR_PARTICIPANT_FIRST_TURN   = "participant.first_turn_index"
ATTR_PARTICIPANT_DIAR_SOURCE  = "participant.diarization_source"
ATTR_PARTICIPANT_CHANNEL_IDENTITY = "participant.channel_identity"
ATTR_STT_SPEAKER_ID           = "stt.speaker_id"

# participant.diarization_source values (framework-agnostic; not LiveKit-specific)
ATTR_DIAR_SOURCE_STT_SPEAKER_ID    = "stt_speaker_id"
ATTR_DIAR_SOURCE_AGENT_ID          = "agent_id"
ATTR_DIAR_SOURCE_POST_SESSION      = "post_session"
ATTR_DIAR_SOURCE_CHANNEL_METADATA  = "channel_metadata"

# Default turn.participant_id before STT speaker_id is known
ATTR_TURN_PARTICIPANT_ID_CALLER    = "caller"

# -- Voice -----------------------------------------------------------------
ATTR_VOICE_STT_LATENCY_MS    = "voice.stt.latency_ms"
ATTR_VOICE_STT_CONFIDENCE    = "voice.stt.confidence"
ATTR_VOICE_TTS_LATENCY_MS    = "voice.tts.latency_ms"
ATTR_VOICE_EOU_LANGUAGE      = "voice.eou.language"
ATTR_VOICE_AMD_CATEGORY      = "voice.amd.category"
ATTR_VOICE_AUDIO_PACKET_LOSS = "voice.audio.packet_loss"
ATTR_VOICE_AUDIO_JITTER_MS   = "voice.audio.jitter_ms"
ATTR_VOICE_DEAD_AIR_MS       = "voice.interaction.dead_air_ms"

# -- Eval (OpenInference, adopted) ----------------------------------------
ATTR_EVAL_NAME        = "eval.name"
ATTR_EVAL_RESULT      = "eval.result"
ATTR_EVAL_SCORE       = "eval.score"
ATTR_EVAL_EXPLANATION = "eval.explanation"

# -- Platform external references (session resolve / debug linking) --------
ATTR_PLATFORM_REF_PREFIX = "platform.ref."  # append kind for flat ref keys
ATTR_PLATFORM_FRAMEWORK = "platform.ref.framework"
ATTR_PLATFORM_KIND      = "platform.ref.kind"
ATTR_PLATFORM_VALUE     = "platform.ref.value"
