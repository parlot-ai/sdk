"""SpanProcessor: remap Pipecat spans onto Conversation Contract + GenAI/voice."""

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
    allocate_agent_turn_index,
    allocate_user_turn_index,
    clear_open_turn_indices,
    close_session,
    configured_agent_id,
    emit_turn,
    ensure_session,
    lookup_session,
    release_agent_turn_reservation,
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
        # conversation_id → (start_ns by turn_number) for duration-preserving remint
        self._turn_starts: dict[str, dict[int, int]] = {}
        # Live parent spans (turn/conversation) so children can read attrs set
        # after start_span (Pipecat sets conversation.id / turn.number post-start).
        self._open_spans: dict[str, Any] = {}
        # conversation_id → turn_number → utterance + timing/latency buffers
        self._utterances: dict[str, dict[int, dict[str, Any]]] = {}
        self._active_conversation_id: str = ""
        self._active_turn_number: int | None = None

    def _bucket(self, cid: str, turn_n: int) -> dict[str, Any]:
        return self._utterances.setdefault(cid, {}).setdefault(turn_n, {})

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
                self._utterances.pop(cid, None)
                self._turn_starts.pop(cid, None)
            return

        if name == NATIVE_TURN:
            self._note_turn_context(attrs, span)
            self._mint_contract_turn(span)
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
        self._buffer_span_timing(span)
        self._map_transcript_text(span)
        self._record_usage_metrics(span)
        # Orphan / tool-continuation TTS: mint agent before the next user STT
        # arrives so indices stay chronological (user N, agent N+1).
        if self._is_tts(name):
            self._maybe_emit_orphan_agent(span)

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
            if cid:
                starts = self._turn_starts.setdefault(cid, {})
                if turn_n not in starts and span.start_time:
                    starts[turn_n] = int(span.start_time)

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

    def _conversation_id_from_context(
        self, attrs: Mapping[str, AttributeValue]
    ) -> str:
        cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
        if cid:
            return cid
        if self._active_conversation_id:
            return self._active_conversation_id
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

    def _find_agent_bucket(
        self, cid: str, prefer_turn: int | None = None
    ) -> tuple[int | None, dict[str, Any]]:
        """Locate a buffer that still holds unemitted agent text."""
        buckets = self._utterances.get(cid) or {}
        if prefer_turn is not None and prefer_turn in buckets:
            b = buckets[prefer_turn]
            if str(b.get("agent") or "").strip() and not b.get("agent_emitted"):
                return prefer_turn, b
        for key, b in list(buckets.items()):
            if str(b.get("agent") or "").strip() and not b.get("agent_emitted"):
                return key if isinstance(key, int) else None, b
        return prefer_turn, {}

    def _flush_pending_agent_only(
        self,
        state: _PipecatSessionState,
        *,
        cid: str,
        prefer_turn: int | None = None,
        interrupted: bool = False,
        e2e: float | None = None,
    ) -> bool:
        """Emit a reserved agent turn (tool continuation or post-STT reply).

        Without this, STT allocates ``user = open_agent + 1`` while keeping the
        old agent index — timeline then sorts user (earlier STT) before agent
        (later LLM) despite a lower agent turn index.

        After STT mints the user turn, ``open_user_turn_index`` stays set with
        ``user_turn_emitted=True`` until the agent reply lands. Allow flush in
        that state so late TTS (native turn already closed) still mints the
        reserved agent index instead of burning it.
        """
        if state.open_agent_turn_index is None:
            return False
        # Still waiting for a paired native-turn mint of the user utterance.
        if state.open_user_turn_index is not None and not state.user_turn_emitted:
            return False
        agent_idx = state.open_agent_turn_index
        _key, buffered = self._find_agent_bucket(cid, prefer_turn)
        agent_text = str(buffered.get("agent") or "").strip()
        if not agent_text:
            # Indices reserved by LLM/TTS with no text yet — drop reservation
            # without burning turn_count (empty TTS / no-audio retry).
            release_agent_turn_reservation(state)
            if state.open_user_turn_index is None:
                state.open_turn_index = None
                state.user_turn_emitted = False
            return False
        agent_start = buffered.get("agent_start_ns")
        agent_end = buffered.get("agent_end_ns")
        llm_ttft = buffered.get("llm_ttft_s")
        tts_ttfb = buffered.get("tts_ttfb_s")
        emit_turn(
            state,
            turn_index=agent_idx,
            role="agent",
            interrupted=interrupted,
            e2e_latency_s=e2e if e2e is not None else _as_float(buffered.get("e2e")),
            llm_ttft_s=float(llm_ttft) if llm_ttft is not None else None,
            tts_ttfb_s=float(tts_ttfb) if tts_ttfb is not None else None,
            agent_text=agent_text,
            start_time_ns=int(agent_start) if agent_start else None,
            end_time_ns=int(agent_end) if agent_end else None,
        )
        buffered["agent_emitted"] = True
        buffered["agent"] = ""
        for key in (
            "agent_start_ns",
            "agent_end_ns",
            "llm_ttft_s",
            "tts_ttfb_s",
            "e2e",
        ):
            buffered.pop(key, None)
        clear_open_turn_indices(state)
        return True

    def _emit_user_from_stt(
        self,
        state: _PipecatSessionState,
        *,
        cid: str,
        turn_n: int | None,
        text: str,
        start_ns: int | None,
        end_ns: int | None,
    ) -> None:
        """Mint the user turn as soon as STT finals (LiveKit-style ordering)."""
        self._flush_pending_agent_only(state, cid=cid, prefer_turn=turn_n)
        if state.user_turn_emitted and state.open_user_turn_index is not None:
            return
        user_idx = allocate_user_turn_index(state)
        allocate_agent_turn_index(state)  # reserve agent slot after user
        emit_turn(
            state,
            turn_index=user_idx,
            role="user",
            user_text=text,
            start_time_ns=start_ns,
            end_time_ns=end_ns,
        )
        state.user_turn_emitted = True
        if turn_n is not None:
            self._bucket(cid, turn_n)["user_emitted"] = True

    def _native_turn_open(self, cid: str) -> bool:
        for sp in self._open_spans.values():
            if (getattr(sp, "name", None) or "") != NATIVE_TURN:
                continue
            attrs = getattr(sp, "attributes", None) or {}
            sp_cid = str(attrs.get(ATTR_PIPECAT_CONVERSATION_ID) or "").strip()
            if sp_cid == cid or (not sp_cid and self._active_conversation_id == cid):
                return True
        return False

    def _maybe_emit_orphan_agent(self, span: ReadableSpan) -> None:
        """Mint agent speech that lands after its native turn already closed.

        Late tool-follow-up TTS otherwise buffers onto the *next* turn and gets
        paired with the next user STT (inverted indices / timeline order).

        Also covers the premature-native-turn case: STT already minted the user
        turn (``user_turn_emitted``) and reserved the agent index, then TTS
        arrives with no open native turn — emit the reserved agent slot now.
        """
        cid, turn_n = self._resolve_conversation_and_turn(span)
        state = lookup_session(cid) if cid else _pipecat_state(get_active_session())
        if state is None or not cid:
            return
        # User slot open but not yet reminted — leave for native-turn mint.
        if state.open_user_turn_index is not None and not state.user_turn_emitted:
            return
        if self._native_turn_open(cid):
            return
        _key, bucket = self._find_agent_bucket(cid, turn_n)
        agent_text = str(bucket.get("agent") or "").strip()
        if not agent_text or bucket.get("agent_emitted"):
            # Late empty TTS (e.g. no-audio retry) may have allocated an
            # agent-only index — roll it back instead of burning the slot.
            if (
                state.open_agent_turn_index is not None
                and state.open_user_turn_index is None
            ):
                release_agent_turn_reservation(state)
            return
        if state.open_agent_turn_index is None:
            allocate_agent_turn_index(state)
        self._flush_pending_agent_only(
            state, cid=cid, prefer_turn=turn_n if turn_n is not None else _key
        )

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
        pipecat_turn = self._turn_number(attrs)
        if pipecat_turn is not None:
            self._active_turn_number = pipecat_turn
        self._active_conversation_id = state.conversation_id
        interrupted = bool(attrs.get(ATTR_PIPECAT_TURN_INTERRUPTED))
        e2e = _as_float(attrs.get(ATTR_PIPECAT_TURN_USER_BOT_LATENCY))
        start_ns = None
        starts = self._turn_starts.get(state.conversation_id) or {}
        if pipecat_turn is not None and pipecat_turn in starts:
            start_ns = starts.pop(pipecat_turn, None)
        end_ns = span.end_time
        buf_key = pipecat_turn if pipecat_turn is not None else -1
        # Flush any prior agent-only reservation *before* popping this turn's
        # bucket (flush reads from ``_utterances``).
        if state.open_user_turn_index is None and state.open_agent_turn_index is not None:
            # Peek whether this turn has user text; if not, we'll emit agent below.
            peek = (self._utterances.get(state.conversation_id) or {}).get(buf_key) or {}
            peek_user = str(peek.get("user") or "").strip()
            if peek_user:
                self._flush_pending_agent_only(
                    state, cid=state.conversation_id, prefer_turn=None
                )

        buffered = (self._utterances.get(state.conversation_id) or {}).pop(buf_key, {})
        user_text = str(buffered.get("user") or "").strip()
        agent_text = str(buffered.get("agent") or "").strip()
        user_already = bool(buffered.get("user_emitted") or state.user_turn_emitted)
        agent_already = bool(buffered.get("agent_emitted"))
        stt_start = buffered.get("stt_start_ns")
        stt_end = buffered.get("stt_end_ns")
        agent_start = buffered.get("agent_start_ns")
        agent_end = buffered.get("agent_end_ns")
        llm_ttft = buffered.get("llm_ttft_s")
        tts_ttfb = buffered.get("tts_ttfb_s")

        user_idx = state.open_user_turn_index
        agent_idx = state.open_agent_turn_index
        if user_text and not user_already and user_idx is None:
            user_idx = allocate_user_turn_index(state)
            agent_idx = allocate_agent_turn_index(state)
        if agent_text and not agent_already and agent_idx is None:
            agent_idx = allocate_agent_turn_index(state)

        # Split wall clocks: shared native-turn bounds made user+agent share
        # the same offset (inflated "gaps"). Prefer STT / LLM+TTS windows.
        user_start = int(stt_start) if stt_start else start_ns
        user_end = int(stt_end) if stt_end else (
            int(agent_start) if agent_start else end_ns
        )
        agent_start_ns = int(agent_start) if agent_start else (
            int(stt_end) if stt_end else start_ns
        )
        agent_end_ns = int(agent_end) if agent_end else end_ns

        if user_text and not user_already and user_idx is not None:
            emit_turn(
                state,
                turn_index=user_idx,
                role="user",
                user_text=user_text,
                start_time_ns=user_start,
                end_time_ns=user_end,
            )
            state.user_turn_emitted = True
        emitted_agent_here = False
        if agent_text and not agent_already and agent_idx is not None:
            emit_turn(
                state,
                turn_index=agent_idx,
                role="agent",
                interrupted=interrupted,
                e2e_latency_s=e2e,
                llm_ttft_s=float(llm_ttft) if llm_ttft is not None else None,
                tts_ttfb_s=float(tts_ttfb) if tts_ttfb is not None else None,
                agent_text=agent_text,
                start_time_ns=agent_start_ns,
                end_time_ns=agent_end_ns,
            )
            emitted_agent_here = True

        # When this native turn had no agent text, mint any reserved agent text
        # sitting in *other* Pipecat-turn buckets (premature native turn closed
        # before TTS; the next native turn must not wipe that reservation).
        if not emitted_agent_here and state.open_agent_turn_index is not None:
            flushed = self._flush_pending_agent_only(
                state,
                cid=state.conversation_id,
                prefer_turn=None,
                interrupted=interrupted,
                e2e=e2e,
            )
            if not flushed and state.open_agent_turn_index is not None:
                release_agent_turn_reservation(state)
        clear_open_turn_indices(state)

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
        """Map pipeline spans onto Parlot turn indices for timeline nesting.

        The app nests ``stt`` / ``llm`` / ``tts`` under **agent** turns only.
        STT at a user-only turn_index shows as an orphan row (odd indentation).
        So we allocate the user index for the utterance row, then stamp STT
        (and LLM/TTS) on the paired agent index.
        """
        name = span.name or ""
        if self._is_stt(name):
            # Tool-continuation may have reserved an agent index with no user.
            # Flush it first so this STT becomes user N / agent N+1 (not N+1 / N).
            self._flush_pending_agent_only(state, cid=state.conversation_id)
            allocate_user_turn_index(state)
            return allocate_agent_turn_index(state)
        if self._is_tts(name) or self._is_llm(name) or self._is_tool(name):
            return allocate_agent_turn_index(state)
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

    def _buffer_span_timing(self, span: ReadableSpan) -> None:
        """Record STT/LLM/TTS windows + TTFB for reminted turn bounds / latency."""
        cid, turn_n = self._resolve_conversation_and_turn(span)
        if not cid or turn_n is None:
            return
        name = span.name or ""
        bucket = self._bucket(cid, turn_n)
        start = span.start_time
        end = span.end_time
        ttfb = _as_float((span.attributes or {}).get(ATTR_PIPECAT_METRICS_TTFB))
        if self._is_stt(name):
            if start:
                bucket["stt_start_ns"] = int(start)
            if end:
                bucket["stt_end_ns"] = int(end)
            return
        if self._is_llm(name) or self._is_tts(name):
            # After an agent-only flush, the next LLM/TTS is a new utterance —
            # do not keep the previous window via min()/max().
            if bucket.get("agent_emitted"):
                bucket["agent_start_ns"] = int(start) if start else None
                bucket["agent_end_ns"] = int(end) if end else None
                bucket.pop("llm_ttft_s", None)
                bucket.pop("tts_ttfb_s", None)
            else:
                if start:
                    prev = bucket.get("agent_start_ns")
                    bucket["agent_start_ns"] = (
                        min(int(prev), int(start)) if prev else int(start)
                    )
                if end:
                    prev_end = bucket.get("agent_end_ns")
                    bucket["agent_end_ns"] = (
                        max(int(prev_end), int(end)) if prev_end else int(end)
                    )
            if ttfb is not None:
                if self._is_llm(name):
                    bucket["llm_ttft_s"] = ttfb
                elif bucket.get("tts_ttfb_s") is None:
                    # Prefer first successful TTFB (retry after "no audio" is noisier).
                    bucket["tts_ttfb_s"] = ttfb

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
        attrs = span.attributes or {}
        name = span.name or ""
        # Prefer final transcripts; interim STT still updates the buffer but we
        # only remint the user turn on finals (or when is_final is absent).
        is_final = attrs.get("is_final")
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
        cid, turn_n = self._resolve_conversation_and_turn(span)
        if self._is_stt(name):
            if not attrs.get(ATTR_TURN_USER_TEXT):
                self._set(span, ATTR_TURN_USER_TEXT, text)
            if not cid:
                return
            if turn_n is not None:
                self._bucket(cid, turn_n)["user"] = text
            # Interim results: keep buffer only.
            if is_final is False:
                return
            state = lookup_session(cid) or _pipecat_state(get_active_session())
            if state is None:
                state = ensure_session(cid)
            if state is None:
                return
            self._emit_user_from_stt(
                state,
                cid=cid,
                turn_n=turn_n,
                text=text,
                start_ns=int(span.start_time) if span.start_time else None,
                end_ns=int(span.end_time) if span.end_time else None,
            )
        elif self._is_tts(name) or self._is_llm(name):
            if not attrs.get(ATTR_TURN_AGENT_TEXT):
                self._set(span, ATTR_TURN_AGENT_TEXT, text)
            if cid and turn_n is None:
                return
            bucket = self._bucket(cid, turn_n) if cid and turn_n is not None else None
            if bucket is None:
                return
            if self._is_tts(name):
                prev = str(bucket.get("agent") or "")
                # Avoid "hello hello" when Pipecat retries / double-fires TTS.
                if prev == text or prev.endswith(text):
                    return
                if text.startswith(prev) and prev:
                    bucket["agent"] = text
                else:
                    bucket["agent"] = f"{prev} {text}".strip() if prev else text
                # New speech after a prior flush (tool then follow-up answer).
                bucket["agent_emitted"] = False
            elif not bucket.get("agent"):
                # LLM output as fallback when TTS never lands text.
                bucket["agent"] = text
                bucket["agent_emitted"] = False
