"""SpanProcessor: remap Pipecat spans onto Conversation Contract + GenAI/voice.

``parlot.turn`` is minted from context-aggregator events (see ``_turn_events``),
not from STT / native-turn / orphan TTS paths. This processor renames pipeline
spans, stamps session linkage + ``turn.index`` for timeline nesting, and maps
metrics / transcript attrs onto those spans.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_ROLE,
    ATTR_GEN_AI_AGENT_ID,
    ATTR_GEN_AI_AGENT_NAME,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_TTS_TTFB_S,
    ATTR_SESSION_AGENT_ID,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_USER_TEXT,
    CONTRACT_SPAN_NAMES,
    is_genai_span_name,
)
from parlot.core.context import ParlotContext
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.session import get_active_session

from ._platform_refs import stamp_pipecat_platform_refs
from ._session import (
    _PipecatSessionState,
    close_session,
    configured_agent_id,
    ensure_session,
    lookup_session,
)
from ._span_rename import (
    NATIVE_CONVERSATION,
    NATIVE_TURN,
    apply_pipecat_span_rename,
    remap_pipecat_span_name,
)
from ._metrics import get_metrics_recorder
from .attrs import (
    ATTR_PIPECAT_CONVERSATION_ID,
    ATTR_PIPECAT_METRICS_AUDIO_SECONDS,
    ATTR_PIPECAT_METRICS_CHAR_COUNT,
    ATTR_PIPECAT_METRICS_TTFB,
    ATTR_PIPECAT_TEXT,
    ATTR_PIPECAT_TRANSCRIPT,
    ATTR_PIPECAT_TURN_NUMBER,
)

logger = logging.getLogger("parlot.instrumentation.pipecat")


def _as_float(value: AttributeValue | None) -> float | None:
    if value is None or isinstance(value, (list, tuple)):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pipecat_state(state: Any) -> _PipecatSessionState | None:
    return state if isinstance(state, _PipecatSessionState) else None


def _span_id_hex(span: Any) -> str:
    try:
        ctx = span.get_span_context()
        span_id = getattr(ctx, "span_id", None) if ctx is not None else None
        if span_id:
            return format(int(span_id), "016x")
    except Exception:
        pass
    return ""


def _parent_span_id_hex(span: ReadableSpan) -> str:
    parent = getattr(span, "parent", None)
    if parent is None:
        return ""
    try:
        return format(int(parent.span_id), "016x")
    except Exception:
        return ""


class PipecatGenAIProcessor(ParlotBaseProcessor):
    """Enrich and remap Pipecat OTEL spans for Parlot export."""

    def __init__(self, *, context: ParlotContext | None = None) -> None:
        self._context = context
        # Live parent spans (turn/conversation) so children can read attrs set
        # after start_span (Pipecat sets conversation.id / turn.number post-start).
        self._open_spans: dict[str, Any] = {}
        self._active_conversation_id: str = ""
        self._active_turn_number: int | None = None

    @staticmethod
    def _debug_log_span(name: str) -> bool:
        """Skip FastAPI/httpx noise when PARLOT_DEBUG_LEVEL=DEBUG."""
        n = (name or "").lower()
        if not n:
            return False
        if n in (NATIVE_CONVERSATION, NATIVE_TURN) or n.startswith("parlot."):
            return True
        if n in ("stt", "tts", "llm") or n.startswith(
            ("stt", "tts", "llm", "chat", "execute_tool")
        ):
            return True
        return False

    def on_start(self, span, parent_context=None) -> None:  # noqa: ANN001
        # SDK Span (not API Span) — leave untyped like LiveKit processor.
        name = getattr(span, "name", None) or ""
        if self._debug_log_span(name):
            super().on_start(span, parent_context)
        sid = _span_id_hex(span)
        if sid and name in (NATIVE_CONVERSATION, NATIVE_TURN):
            self._open_spans[sid] = span
        # Activate session as early as possible so INFO logs correlate.
        if name == NATIVE_TURN:
            parent_attrs = self._parent_attrs(span)
            cid = str(
                (getattr(span, "attributes", None) or {}).get(ATTR_PIPECAT_CONVERSATION_ID)
                or parent_attrs.get(ATTR_PIPECAT_CONVERSATION_ID)
                or self._active_conversation_id
                or ""
            ).strip()
            if cid:
                self._active_conversation_id = cid
                ensure_session(cid)

    def on_end(self, span: ReadableSpan) -> None:
        name = span.name or ""
        if self._debug_log_span(name):
            super().on_end(span)
        attrs = span.attributes or {}
        sid = ""
        try:
            ctx = span.get_span_context()
            if ctx is not None:
                sid = format(int(ctx.span_id), "016x")
        except Exception:
            sid = ""
        if sid:
            self._open_spans.pop(sid, None)

        # Passthrough contract / GenAI spans we mint (emit_turn / ensure_session).
        if name in CONTRACT_SPAN_NAMES or is_genai_span_name(name):
            return

        if name == NATIVE_CONVERSATION:
            cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
            if cid:
                self._active_conversation_id = cid
                ensure_session(cid)
                span._name = "__parlot_drop_conversation__"
                close_session(cid, reason="completed")
            return

        if name == NATIVE_TURN:
            self._note_turn_context(attrs, span)
            # Contract turns come from aggregator events — drop native turn only.
            span._name = "__parlot_drop_turn__"
            return

        exported = remap_pipecat_span_name(name, attrs)
        if exported is None:
            span._name = f"__parlot_drop_{name}__"
            return

        apply_pipecat_span_rename(span)
        self._stamp_session_linkage(span)
        self._stamp_agent_role(span)
        self._map_pipecat_metrics(span)
        self._map_transcript_text(span)
        self._record_usage_metrics(span)

    def _note_turn_context(
        self, attrs: Mapping[str, AttributeValue], span: ReadableSpan
    ) -> None:
        cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
        turn_n = self._turn_number(attrs)
        if cid:
            self._active_conversation_id = cid
            ensure_session(cid)
        if turn_n is not None:
            self._active_turn_number = turn_n

    def _parent_attrs(self, span: ReadableSpan) -> Mapping[str, AttributeValue]:
        parent_id = _parent_span_id_hex(span)
        if not parent_id:
            return {}
        parent = self._open_spans.get(parent_id)
        if parent is None:
            return {}
        return getattr(parent, "attributes", None) or {}

    def _resolve_conversation_and_turn(
        self, span: ReadableSpan
    ) -> tuple[str, int | None]:
        attrs = span.attributes or {}
        parent_attrs = self._parent_attrs(span)
        cid = str(
            attrs.get(ATTR_PIPECAT_CONVERSATION_ID)
            or parent_attrs.get(ATTR_PIPECAT_CONVERSATION_ID)
            or self._active_conversation_id
            or ""
        ).strip()
        if not cid:
            state = _pipecat_state(get_active_session())
            if state and state.conversation_id:
                cid = state.conversation_id
        turn_n = self._turn_number(attrs) or self._turn_number(parent_attrs)
        if turn_n is None:
            turn_n = self._active_turn_number
        if turn_n is None:
            state = lookup_session(cid) if cid else _pipecat_state(get_active_session())
            if state and state.open_turn_index is not None:
                turn_n = state.open_turn_index
        return cid, turn_n

    @staticmethod
    def _turn_number(attrs: Mapping[str, AttributeValue]) -> int | None:
        raw = attrs.get(ATTR_PIPECAT_TURN_NUMBER)
        if raw is None or isinstance(raw, (list, tuple)):
            return None
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_stt(name: str) -> bool:
        return name == "stt" or name.startswith("stt")

    @staticmethod
    def _is_tts(name: str) -> bool:
        return name == "tts" or name.startswith("tts")

    @staticmethod
    def _is_llm(name: str) -> bool:
        # Native ``llm`` before rename, or GenAI ``chat`` / ``chat {model}`` after.
        if name.startswith("llm_tool"):
            return False
        return (
            name == "llm"
            or name.startswith("llm")
            or name == "chat"
            or name.startswith("chat")
        )

    @staticmethod
    def _is_tool(name: str) -> bool:
        return name.startswith("execute_tool") or name.startswith("llm_tool")

    def _parlot_turn_index_for_span(
        self, span: ReadableSpan, state: _PipecatSessionState
    ) -> int | None:
        """Stamp pipeline spans with open aggregator indices (no new allocation).

        The app nests ``stt`` / ``llm`` / ``tts`` under **agent** turns. Indices
        are reserved when aggregator events mint ``parlot.turn`` — do not burn
        new indices from STT/TTS end alone.
        """
        name = span.name or ""
        if self._is_stt(name) or self._is_tts(name) or self._is_llm(name) or self._is_tool(
            name
        ):
            if state.open_agent_turn_index is not None:
                return state.open_agent_turn_index
            if state.open_user_turn_index is not None:
                return state.open_user_turn_index
            if state.turn_count > 0:
                return state.turn_count
            return None
        return state.open_agent_turn_index or state.open_user_turn_index

    def _stamp_session_linkage(self, span: ReadableSpan) -> None:
        cid, pipecat_turn = self._resolve_conversation_and_turn(span)
        state = lookup_session(cid) if cid else _pipecat_state(get_active_session())
        if state is None and cid:
            state = ensure_session(cid)
        if state is None:
            return
        if cid:
            self._active_conversation_id = cid
        if pipecat_turn is not None:
            self._active_turn_number = pipecat_turn
        parlot_turn = self._parlot_turn_index_for_span(span, state)
        self._set(span, ATTR_SESSION_ID, state.session_id)
        self._set(span, ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        if parlot_turn is not None:
            self._set(span, ATTR_TURN_INDEX, parlot_turn)
        agent_id = configured_agent_id()
        if agent_id:
            self._set(span, ATTR_GEN_AI_AGENT_ID, agent_id)
            self._set(span, ATTR_GEN_AI_AGENT_NAME, agent_id)
            self._set(span, ATTR_SESSION_AGENT_ID, agent_id)
        stamp_pipecat_platform_refs(span, conversation_id=state.conversation_id)

    def _stamp_agent_role(self, span: ReadableSpan) -> None:
        name = span.name or ""
        attrs = span.attributes or {}
        if attrs.get(ATTR_AGENT_ROLE):
            return
        if self._is_stt(name):
            self._set(span, ATTR_AGENT_ROLE, "stt")
        elif self._is_tts(name):
            self._set(span, ATTR_AGENT_ROLE, "tts")
        elif self._is_llm(name):
            self._set(span, ATTR_AGENT_ROLE, "llm")
        elif self._is_tool(name):
            self._set(span, ATTR_AGENT_ROLE, "tool")

    def _map_pipecat_metrics(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        name = span.name or ""
        ttfb = _as_float(attrs.get(ATTR_PIPECAT_METRICS_TTFB))
        # Only TTS owns gen_ai.tts.ttfb_s — do not stamp LLM TTFB there.
        if (
            ttfb is not None
            and self._is_tts(name)
            and not attrs.get(ATTR_GEN_AI_TTS_TTFB_S)
        ):
            self._set(span, ATTR_GEN_AI_TTS_TTFB_S, ttfb)
        if not attrs.get(ATTR_GEN_AI_MODEL):
            model = attrs.get("gen_ai.request.model") or attrs.get("model")
            if model is not None and not isinstance(model, (list, tuple)):
                self._set(span, ATTR_GEN_AI_MODEL, str(model))

    def _record_usage_metrics(self, span: ReadableSpan) -> None:
        recorder = get_metrics_recorder()
        if recorder is None:
            return
        attrs = span.attributes or {}
        session_id = str(attrs.get(ATTR_SESSION_ID) or "").strip()
        if not session_id:
            return
        name = span.name or ""
        model = str(attrs.get(ATTR_GEN_AI_MODEL) or attrs.get("gen_ai.request.model") or "")
        provider = str(attrs.get("gen_ai.provider.name") or "")
        if self._is_stt(name):
            audio = _as_float(attrs.get(ATTR_PIPECAT_METRICS_AUDIO_SECONDS))
            if audio:
                recorder.record_stt_audio(
                    session_id=session_id,
                    audio_seconds=audio,
                    model=model,
                    provider=provider,
                )
        elif self._is_tts(name):
            raw_chars = attrs.get(ATTR_PIPECAT_METRICS_CHAR_COUNT)
            try:
                chars = int(raw_chars) if raw_chars is not None else 0  # type: ignore[arg-type]
            except (TypeError, ValueError):
                chars = 0
            if chars:
                recorder.record_tts_characters(
                    session_id=session_id,
                    characters=chars,
                    model=model,
                    provider=provider,
                )
        elif self._is_llm(name):
            try:
                tin = int(attrs.get("gen_ai.usage.input_tokens") or 0)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                tin = 0
            try:
                tout = int(attrs.get("gen_ai.usage.output_tokens") or 0)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                tout = 0
            if tin or tout:
                recorder.record_llm_tokens(
                    session_id=session_id,
                    input_tokens=tin,
                    output_tokens=tout,
                    model=model,
                    provider=provider,
                )
                # Keep session totals for session.* close histograms.
                cid = str(
                    attrs.get(ATTR_SESSION_CONVERSATION_ID)
                    or attrs.get(ATTR_PIPECAT_CONVERSATION_ID)
                    or ""
                ).strip()
                sess = lookup_session(cid) if cid else _pipecat_state(get_active_session())
                if sess is not None and sess.session_id == session_id:
                    if tin:
                        sess.total_input_tokens += tin
                    if tout:
                        sess.total_output_tokens += tout

    def _map_transcript_text(self, span: ReadableSpan) -> None:
        """Stamp transcript attrs on pipeline spans for nesting; do not mint turns."""
        attrs = span.attributes or {}
        name = span.name or ""
        transcript = (
            attrs.get(ATTR_PIPECAT_TRANSCRIPT)
            or attrs.get(ATTR_PIPECAT_TEXT)
            or attrs.get("output")
        )
        if transcript is None or isinstance(transcript, (list, tuple)):
            return
        text = str(transcript).strip()
        if not text:
            return
        if self._is_stt(name):
            if not attrs.get(ATTR_TURN_USER_TEXT):
                self._set(span, ATTR_TURN_USER_TEXT, text)
        elif self._is_tts(name) or self._is_llm(name):
            if not attrs.get(ATTR_TURN_AGENT_TEXT):
                self._set(span, ATTR_TURN_AGENT_TEXT, text)
