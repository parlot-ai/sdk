"""
Semantic convention attribute name constants for Parlot instrumentation.

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
# Layer 3 — Parlot extensions
# ---------------------------------------------------------------------------

# -- Agent identity (gaps the OTel spec does not cover) --------------------
ATTR_AGENT_ROLE      = "agent.role"       # orchestrator | task | tool | guardrail | stt | tts | llm | amd
ATTR_AGENT_FRAMEWORK = "agent.framework"  # livekit | crewai | langgraph | adk | custom

# -- Agent coordination ----------------------------------------------------
ATTR_AGENT_TRANSFER_FROM    = "agent.transfer.from_agent_id"
ATTR_AGENT_TRANSFER_TO      = "agent.transfer.to_agent_id"
ATTR_AGENT_TRANSFER_REASON  = "agent.transfer.reason"
ATTR_AGENT_TRANSFER_BYTES   = "agent.transfer.context_payload_bytes"
ATTR_AGENT_COORD_OVERHEAD   = "agent.coordination.overhead_ms"

# -- Session ---------------------------------------------------------------
ATTR_SESSION_ID             = "session.id"
ATTR_SESSION_CONVERSATION_ID = "session.conversation_id"
ATTR_SESSION_MODALITY       = "session.modality"         # voice | text | multimodal
ATTR_SESSION_PARTICIPANT_COUNT = "session.participant_count"
ATTR_SESSION_INTENT_LABEL   = "session.intent_label"
ATTR_SESSION_CONTACT_TYPE   = "session.contact_type"     # human | voicemail | ivr | unavailable | unknown

# -- Conversation ----------------------------------------------------------
ATTR_CONVERSATION_ID      = "conversation.id"
ATTR_CONVERSATION_CHANNEL = "conversation.channel"  # voice | webchat | sms | whatsapp

# -- Turn ------------------------------------------------------------------
ATTR_TURN_PREV_TRACE_ID     = "turn.prev_trace_id"
ATTR_TURN_INDEX             = "turn.index"
ATTR_TURN_PARTICIPANT_ID    = "turn.participant_id"
ATTR_TURN_PARTICIPANT_ROLE  = "turn.participant_role"
ATTR_TURN_PARTICIPANT_LABEL = "turn.participant_label"
ATTR_TURN_MEDIA_START_MS    = "turn.media_segment_start_ms"
ATTR_TURN_MEDIA_END_MS      = "turn.media_segment_end_ms"
ATTR_TURN_INTERRUPTED       = "turn.interrupted"

# -- Participant / Diarization ---------------------------------------------
ATTR_PARTICIPANT_ID           = "participant.id"
ATTR_PARTICIPANT_ROLE         = "participant.role"
ATTR_PARTICIPANT_LABEL        = "participant.label"
ATTR_PARTICIPANT_FIRST_TURN   = "participant.first_turn_index"
ATTR_PARTICIPANT_DIAR_SOURCE  = "participant.diarization_source"

# -- Voice -----------------------------------------------------------------
ATTR_VOICE_STT_LATENCY_MS    = "voice.stt.latency_ms"
ATTR_VOICE_STT_CONFIDENCE    = "voice.stt.confidence"
ATTR_VOICE_TTS_LATENCY_MS    = "voice.tts.latency_ms"
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

# ---------------------------------------------------------------------------
# LiveKit-native attribute names (emitted by livekit-agents SDK directly)
# Used by instrumentation-livekit; defined here so they can be imported
# without taking a hard dep on livekit-agents.
# ---------------------------------------------------------------------------

ATTR_LK_JOB_ID          = "lk.job_id"
ATTR_LK_AGENT_NAME      = "lk.agent_name"
ATTR_LK_AGENT_LABEL     = "lk.agent_label"
ATTR_LK_ROOM_NAME       = "lk.room_name"
ATTR_LK_ROOM_SID        = "lk.room.sid"

ATTR_LK_TURN_ID         = "lk.generation_id"
ATTR_LK_PARENT_TURN_ID  = "lk.parent_generation_id"
ATTR_LK_USER_INPUT      = "lk.user_input"
ATTR_LK_INSTRUCTIONS    = "lk.instructions"
ATTR_LK_INTERRUPTED     = "lk.interrupted"
ATTR_LK_IS_INTERRUPTION = "lk.is_interruption"
ATTR_LK_SPEECH_ID       = "lk.speech_id"
ATTR_LK_RESPONSE_TEXT   = "lk.response.text"
ATTR_LK_E2E_LATENCY     = "lk.e2e_latency"
ATTR_LK_CHAT_CTX        = "lk.chat_ctx"
ATTR_LK_RESPONSE_TTFT   = "lk.response.ttft"
ATTR_LK_TTS_INPUT_TEXT  = "lk.input_text"
ATTR_LK_RESPONSE_TTFB   = "lk.response.ttfb"

ATTR_LK_FNC_TOOL_ID     = "lk.function_tool.id"
ATTR_LK_FNC_TOOL_NAME   = "lk.function_tool.name"
ATTR_LK_FNC_TOOL_ARGS   = "lk.function_tool.arguments"
ATTR_LK_FNC_TOOL_OUTPUT = "lk.function_tool.output"
ATTR_LK_FNC_TOOL_ERROR  = "lk.function_tool.is_error"

ATTR_LK_TURN_INDEX         = "lk.turn_index"
ATTR_LK_TOOL_CALL_INDEX    = "lk.tool_call_index"
ATTR_LK_HANDOFF_INDEX      = "lk.handoff_index"
ATTR_LK_HANDOFF_TARGET     = "lk.handoff.target_agent"
ATTR_LK_HANDOFF_SOURCE     = "lk.handoff.source_agent_id"
ATTR_LK_HANDOFF_TRANSITION = "lk.handoff.transition_latency_ms"
ATTR_LK_HANDOFF_ITEM_ID    = "lk.handoff.item_id"
ATTR_LK_HANDOFF_CREATED_AT = "lk.handoff.created_at"
ATTR_LK_TURN_E2E_LATENCY   = "lk.turn.e2e_latency_s"
ATTR_LK_TURN_INTERRUPTED   = "lk.turn.interrupted"

ATTR_LK_SESSION_TURNS        = "lk.session.turn_count"
ATTR_LK_SESSION_TOOL_CALLS   = "lk.session.tool_call_count"
ATTR_LK_SESSION_HANDOFFS     = "lk.session.handoff_count"
ATTR_LK_SESSION_INPUT_TOKENS = "lk.session.total_input_tokens"
ATTR_LK_SESSION_OUT_TOKENS   = "lk.session.total_output_tokens"
ATTR_LK_SESSION_COST_USD     = "lk.session.total_cost_usd"
ATTR_LK_SESSION_AGENT_CHAIN  = "lk.session.agent_chain"
