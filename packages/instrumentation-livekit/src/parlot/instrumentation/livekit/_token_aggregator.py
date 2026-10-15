"""Session and span token accumulation for LiveKit GenAI enrichment."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_GEN_AI_CACHE_HIT_RATE,
    ATTR_GEN_AI_CACHED_TOKENS,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
)
from parlot.instrumentation.livekit.attrs import ATTR_LK_SPEECH_ID
from ._session import get_job_bootstrap
from ._session_state import _LiveKitSessionState
from ._span_util import attr_int

SetAttrFn = Callable[[ReadableSpan, str, AttributeValue], None]

# LiveKit OTEL / GenAI alias for cache-read tokens (subset of input).
_ATTR_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"


class TokenAggregator:
    """Owns session usage totals and LLM request / plugin token attachment."""

    def __init__(
        self,
        *,
        set_attr: SetAttrFn,
        plugin_host: Any,
    ) -> None:
        self._set = set_attr
        self._plugin_host = plugin_host

    def apply_session_usage(
        self,
        total_in: int,
        total_out: int,
        total_cached: int = 0,
    ) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        state.total_input_tokens = max(total_in, 0)
        state.total_output_tokens = max(total_out, 0)
        state.total_cached_tokens = max(total_cached, 0)
        state.usage_from_events = True

    def accumulate_llm_request_tokens(
        self,
        span: ReadableSpan,
        state: _LiveKitSessionState,
        attrs: Mapping[str, AttributeValue],
    ) -> None:
        input_tokens = attr_int(attrs, ATTR_GEN_AI_IN_TOKENS)
        output_tokens = attr_int(attrs, ATTR_GEN_AI_OUT_TOKENS)
        cached_tokens = attr_int(attrs, ATTR_GEN_AI_CACHED_TOKENS)
        if cached_tokens <= 0:
            cached_tokens = attr_int(attrs, _ATTR_CACHE_READ_INPUT_TOKENS)

        if not state.usage_from_events:
            state.total_input_tokens += input_tokens
            state.total_output_tokens += output_tokens
            state.total_cached_tokens += cached_tokens

        if cached_tokens > 0 and not attrs.get(ATTR_GEN_AI_CACHED_TOKENS):
            self._set(span, ATTR_GEN_AI_CACHED_TOKENS, cached_tokens)

        if input_tokens and cached_tokens:
            self._set(
                span,
                ATTR_GEN_AI_CACHE_HIT_RATE,
                round(cached_tokens / input_tokens, 4),
            )

    def apply_plugin_llm_usage_to_span(
        self,
        span: ReadableSpan,
        attrs: Mapping[str, AttributeValue],
        *,
        prefer_fifo: bool = False,
    ) -> None:
        has_in_out = bool(
            attrs.get(ATTR_GEN_AI_IN_TOKENS) or attrs.get(ATTR_GEN_AI_OUT_TOKENS)
        )
        has_cached = bool(
            attrs.get(ATTR_GEN_AI_CACHED_TOKENS)
            or attrs.get(_ATTR_CACHE_READ_INPUT_TOKENS)
        )
        if has_in_out and has_cached:
            return

        from ._plugin_metrics import resolve_llm_usage_for_span

        speech_id = str(attrs.get(ATTR_LK_SPEECH_ID, "") or "")
        # When input/output are already present, peek without consuming the FIFO
        # so we only fill missing cached tokens.
        if has_in_out and not has_cached:
            usage = self._peek_llm_usage(speech_id=speech_id)
            if usage is not None and usage.prompt_cached_tokens > 0:
                self._set(
                    span, ATTR_GEN_AI_CACHED_TOKENS, usage.prompt_cached_tokens
                )
                if usage.prompt_tokens > 0:
                    self._set(
                        span,
                        ATTR_GEN_AI_CACHE_HIT_RATE,
                        round(usage.prompt_cached_tokens / usage.prompt_tokens, 4),
                    )
            return

        usage = resolve_llm_usage_for_span(
            self._plugin_host, speech_id=speech_id, prefer_fifo=prefer_fifo
        )
        if usage is None:
            return
        if usage.prompt_tokens > 0:
            self._set(span, ATTR_GEN_AI_IN_TOKENS, usage.prompt_tokens)
        if usage.completion_tokens > 0:
            self._set(span, ATTR_GEN_AI_OUT_TOKENS, usage.completion_tokens)
        if usage.prompt_cached_tokens > 0:
            self._set(span, ATTR_GEN_AI_CACHED_TOKENS, usage.prompt_cached_tokens)
            if usage.prompt_tokens > 0:
                self._set(
                    span,
                    ATTR_GEN_AI_CACHE_HIT_RATE,
                    round(usage.prompt_cached_tokens / usage.prompt_tokens, 4),
                )
        if usage.model_name and not attrs.get(ATTR_GEN_AI_MODEL):
            self._set(span, ATTR_GEN_AI_MODEL, usage.model_name)
        if usage.model_provider and not attrs.get(ATTR_GEN_AI_PROVIDER):
            self._set(span, ATTR_GEN_AI_PROVIDER, usage.model_provider)

    def _peek_llm_usage(self, *, speech_id: str = ""):
        from ._plugin_metrics import _plugin_state

        plugin_state = _plugin_state(self._plugin_host)
        sid = speech_id.strip()
        if sid:
            queue = plugin_state.by_speech_id.get(sid)
            if queue:
                return queue[0]
        if plugin_state.llm_queue:
            return plugin_state.llm_queue[0]
        return None
