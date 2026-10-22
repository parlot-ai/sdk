"""SpanProcessor: remap Pipecat spans onto Conversation Contract + GenAI/voice."""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Span

from parlot.core.attrs import (
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_TTS_TTFB_S,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_INDEX,
    ATTR_TURN_USER_TEXT,
)
from parlot.core.context import ParlotContext
from parlot.core.processor import ParlotBaseProcessor
from parlot.core.session import get_active_session

from ._session import close_session, emit_turn, ensure_session, lookup_session
from ._span_rename import (
    NATIVE_CONVERSATION,
    NATIVE_TURN,
    apply_pipecat_span_rename,
    remap_pipecat_span_name,
)
from ._platform_refs import stamp_pipecat_platform_refs
from .attrs import (
    ATTR_PIPECAT_CONVERSATION_ID,
    ATTR_PIPECAT_METRICS_TTFB,
    ATTR_PIPECAT_TEXT,
    ATTR_PIPECAT_TRANSCRIPT,
    ATTR_PIPECAT_TURN_INTERRUPTED,
    ATTR_PIPECAT_TURN_NUMBER,
    ATTR_PIPECAT_TURN_USER_BOT_LATENCY,
)

logger = logging.getLogger("parlot.instrumentation.pipecat")


class PipecatGenAIProcessor(ParlotBaseProcessor):
    """Enrich and remap Pipecat OTEL spans for Parlot export."""

    def __init__(self, *, context: ParlotContext | None = None) -> None:
        self._context = context
        # conversation_id → (start_ns by turn_number) for duration-preserving remint
        self._turn_starts: dict[str, dict[int, int]] = {}

    def on_start(self, span: Span, parent_context: Any = None) -> None:
        super().on_start(span, parent_context)
        name = span.name or ""
        attrs = span.attributes or {}
        if name == NATIVE_CONVERSATION:
            cid = str(
                attrs.get(ATTR_PIPECAT_CONVERSATION_ID)
                or attrs.get(ATTR_SESSION_CONVERSATION_ID)
                or ""
            ).strip()
            if cid:
                ensure_session(cid)
        elif name == NATIVE_TURN:
            cid = self._conversation_id_from_context(attrs, parent_context)
            turn_n = self._turn_number(attrs)
            if cid and turn_n is not None:
                ensure_session(cid)
                starts = self._turn_starts.setdefault(cid, {})
                starts[turn_n] = span.start_time or 0

    def on_end(self, span: ReadableSpan) -> None:
        super().on_end(span)
        name = span.name or ""
        attrs = span.attributes or {}

        if name == NATIVE_CONVERSATION:
            cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
            if cid:
                # Session span already minted; drop native conversation from export
                # by renaming to a non-exportable name then clearing — ExportFilter
                # drops unknown names. Prefer marking via empty rename.
                span._name = "__parlot_drop_conversation__"
                close_session(cid, reason="completed")
            return

        if name == NATIVE_TURN:
            self._mint_contract_turn(span)
            span._name = "__parlot_drop_turn__"
            return

        exported = remap_pipecat_span_name(name, attrs)
        if exported is None:
            span._name = f"__parlot_drop_{name}__"
            return

        apply_pipecat_span_rename(span)
        self._stamp_session_linkage(span)
        self._map_pipecat_metrics(span)
        self._map_transcript_text(span)

    def _conversation_id_from_context(
        self, attrs: Any, parent_context: Any
    ) -> str:
        cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
        if cid:
            return cid
        state = get_active_session()
        if state and getattr(state, "conversation_id", ""):
            return str(state.conversation_id)
        return ""

    @staticmethod
    def _turn_number(attrs: Any) -> int | None:
        raw = attrs.get(ATTR_PIPECAT_TURN_NUMBER)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _mint_contract_turn(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
        state = lookup_session(cid) if cid else get_active_session()
        if state is None or not getattr(state, "conversation_id", ""):
            # Best-effort: open session from turn attrs
            if not cid:
                return
            state = ensure_session(cid)
        if state is None:
            return
        turn_n = self._turn_number(attrs)
        if turn_n is None:
            state.turn_count += 1
            turn_n = state.turn_count
        interrupted = bool(attrs.get(ATTR_PIPECAT_TURN_INTERRUPTED))
        latency = attrs.get(ATTR_PIPECAT_TURN_USER_BOT_LATENCY)
        e2e: float | None = None
        if latency is not None:
            try:
                e2e = float(latency)
            except (TypeError, ValueError):
                e2e = None
        start_ns = None
        starts = self._turn_starts.get(state.conversation_id) or {}
        if turn_n in starts:
            start_ns = starts.pop(turn_n, None)
        end_ns = span.end_time
        emit_turn(
            state,
            turn_index=turn_n,
            role="agent",
            interrupted=interrupted,
            e2e_latency_s=e2e,
            start_time_ns=start_ns,
            end_time_ns=end_ns,
        )

    def _stamp_session_linkage(self, span: ReadableSpan) -> None:
        state = get_active_session()
        if state is None or not state.session_id:
            # Try conversation.id on the span itself
            attrs = span.attributes or {}
            cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
            if cid:
                state = ensure_session(cid)
        if state is None:
            return
        self._set(span, ATTR_SESSION_ID, state.session_id)
        self._set(span, ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        turn_n = self._turn_number(span.attributes or {})
        if turn_n is None and getattr(state, "open_turn_index", None) is not None:
            turn_n = state.open_turn_index
        if turn_n is not None:
            self._set(span, ATTR_TURN_INDEX, turn_n)
        stamp_pipecat_platform_refs(span, conversation_id=state.conversation_id)

    def _map_pipecat_metrics(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        ttfb = attrs.get(ATTR_PIPECAT_METRICS_TTFB)
        if ttfb is not None and not attrs.get(ATTR_GEN_AI_TTS_TTFB_S):
            try:
                self._set(span, ATTR_GEN_AI_TTS_TTFB_S, float(ttfb))
            except (TypeError, ValueError):
                pass
        # Pipecat sometimes uses gen_ai.usage.* already — leave alone.
        # Ensure model attr present when provider set.
        if not attrs.get(ATTR_GEN_AI_MODEL):
            model = attrs.get("gen_ai.request.model") or attrs.get("model")
            if model:
                self._set(span, ATTR_GEN_AI_MODEL, str(model))

    def _map_transcript_text(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        name = span.name or ""
        transcript = attrs.get(ATTR_PIPECAT_TRANSCRIPT) or attrs.get(ATTR_PIPECAT_TEXT)
        if not transcript:
            return
        text = str(transcript)
        if name == "stt" or name.startswith("stt"):
            if not attrs.get(ATTR_TURN_USER_TEXT):
                self._set(span, ATTR_TURN_USER_TEXT, text)
        elif name == "tts" or name.startswith("tts") or name.startswith("chat"):
            if not attrs.get(ATTR_TURN_AGENT_TEXT):
                self._set(span, ATTR_TURN_AGENT_TEXT, text)
