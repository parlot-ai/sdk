"""SpanProcessor: remap Pipecat spans onto Conversation Contract + GenAI/voice."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_TTS_TTFB_S,
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
    emit_turn,
    ensure_session,
    lookup_session,
)
from ._span_rename import (
    NATIVE_CONVERSATION,
    NATIVE_TURN,
    apply_pipecat_span_rename,
    remap_pipecat_span_name,
)
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


def _as_float(value: AttributeValue | None) -> float | None:
    if value is None or isinstance(value, (list, tuple)):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pipecat_state(state: Any) -> _PipecatSessionState | None:
    return state if isinstance(state, _PipecatSessionState) else None


class PipecatGenAIProcessor(ParlotBaseProcessor):
    """Enrich and remap Pipecat OTEL spans for Parlot export."""

    def __init__(self, *, context: ParlotContext | None = None) -> None:
        self._context = context
        # conversation_id → (start_ns by turn_number) for duration-preserving remint
        self._turn_starts: dict[str, dict[int, int]] = {}

    def on_start(self, span, parent_context=None) -> None:  # noqa: ANN001
        # SDK Span (not API Span) — leave untyped like LiveKit processor.
        super().on_start(span, parent_context)
        name = getattr(span, "name", None) or ""
        attrs: Mapping[str, AttributeValue] = getattr(span, "attributes", None) or {}
        if name == NATIVE_CONVERSATION:
            cid = str(
                attrs.get(ATTR_PIPECAT_CONVERSATION_ID)
                or attrs.get(ATTR_SESSION_CONVERSATION_ID)
                or ""
            ).strip()
            if cid:
                ensure_session(cid)
        elif name == NATIVE_TURN:
            cid = self._conversation_id_from_context(attrs)
            turn_n = self._turn_number(attrs)
            if cid and turn_n is not None:
                ensure_session(cid)
                starts = self._turn_starts.setdefault(cid, {})
                start_time = getattr(span, "start_time", None)
                starts[turn_n] = int(start_time) if start_time else 0

    def on_end(self, span: ReadableSpan) -> None:
        super().on_end(span)
        name = span.name or ""
        attrs = span.attributes or {}

        # Passthrough contract / GenAI spans we mint (emit_turn / ensure_session).
        # Remap treats unknown names as drop — without this, parlot.session /
        # parlot.turn never export. Do not early-return on bare "stt"/"tts":
        # those are Pipecat-native names that still need linkage enrichment.
        if name in CONTRACT_SPAN_NAMES or is_genai_span_name(name):
            return

        if name == NATIVE_CONVERSATION:
            cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
            if cid:
                # Session span already minted; drop native conversation from export.
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
        self, attrs: Mapping[str, AttributeValue]
    ) -> str:
        cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
        if cid:
            return cid
        state = _pipecat_state(get_active_session())
        if state and state.conversation_id:
            return state.conversation_id
        return ""

    @staticmethod
    def _turn_number(attrs: Mapping[str, AttributeValue]) -> int | None:
        raw = attrs.get(ATTR_PIPECAT_TURN_NUMBER)
        if raw is None or isinstance(raw, (list, tuple)):
            return None
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _mint_contract_turn(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
        state = lookup_session(cid) if cid else _pipecat_state(get_active_session())
        if state is None or not state.conversation_id:
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
        e2e = _as_float(attrs.get(ATTR_PIPECAT_TURN_USER_BOT_LATENCY))
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
        state = _pipecat_state(get_active_session())
        if state is None or not state.session_id:
            attrs = span.attributes or {}
            cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
            if cid:
                state = ensure_session(cid)
        if state is None:
            return
        self._set(span, ATTR_SESSION_ID, state.session_id)
        self._set(span, ATTR_SESSION_CONVERSATION_ID, state.conversation_id)
        turn_n = self._turn_number(span.attributes or {})
        if turn_n is None and state.open_turn_index is not None:
            turn_n = state.open_turn_index
        if turn_n is not None:
            self._set(span, ATTR_TURN_INDEX, turn_n)
        stamp_pipecat_platform_refs(span, conversation_id=state.conversation_id)

    def _map_pipecat_metrics(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        ttfb = _as_float(attrs.get(ATTR_PIPECAT_METRICS_TTFB))
        if ttfb is not None and not attrs.get(ATTR_GEN_AI_TTS_TTFB_S):
            self._set(span, ATTR_GEN_AI_TTS_TTFB_S, ttfb)
        if not attrs.get(ATTR_GEN_AI_MODEL):
            model = attrs.get("gen_ai.request.model") or attrs.get("model")
            if model is not None and not isinstance(model, (list, tuple)):
                self._set(span, ATTR_GEN_AI_MODEL, str(model))

    def _map_transcript_text(self, span: ReadableSpan) -> None:
        attrs = span.attributes or {}
        name = span.name or ""
        transcript = attrs.get(ATTR_PIPECAT_TRANSCRIPT) or attrs.get(ATTR_PIPECAT_TEXT)
        if transcript is None or isinstance(transcript, (list, tuple)):
            return
        text = str(transcript)
        if name == "stt" or name.startswith("stt"):
            if not attrs.get(ATTR_TURN_USER_TEXT):
                self._set(span, ATTR_TURN_USER_TEXT, text)
        elif name == "tts" or name.startswith("tts") or name.startswith("chat"):
            if not attrs.get(ATTR_TURN_AGENT_TEXT):
                self._set(span, ATTR_TURN_AGENT_TEXT, text)
