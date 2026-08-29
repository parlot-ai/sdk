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

    def apply_session_usage(self, total_in: int, total_out: int) -> None:
        bootstrap = get_job_bootstrap()
        if bootstrap is None:
            return
        state = bootstrap.state
        state.total_input_tokens = max(total_in, 0)
        state.total_output_tokens = max(total_out, 0)
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

        if not state.usage_from_events:
            state.total_input_tokens += input_tokens
            state.total_output_tokens += output_tokens

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
        if attrs.get(ATTR_GEN_AI_IN_TOKENS) or attrs.get(ATTR_GEN_AI_OUT_TOKENS):
            return
        from ._plugin_metrics import resolve_llm_usage_for_span

        speech_id = str(attrs.get(ATTR_LK_SPEECH_ID, "") or "")
        usage = resolve_llm_usage_for_span(
            self._plugin_host, speech_id=speech_id, prefer_fifo=prefer_fifo
        )
        if usage is None:
            return
        if usage.prompt_tokens > 0:
            self._set(span, ATTR_GEN_AI_IN_TOKENS, usage.prompt_tokens)
        if usage.completion_tokens > 0:
            self._set(span, ATTR_GEN_AI_OUT_TOKENS, usage.completion_tokens)
        if usage.model_name and not attrs.get(ATTR_GEN_AI_MODEL):
            self._set(span, ATTR_GEN_AI_MODEL, usage.model_name)
        if usage.model_provider and not attrs.get(ATTR_GEN_AI_PROVIDER):
            self._set(span, ATTR_GEN_AI_PROVIDER, usage.model_provider)
