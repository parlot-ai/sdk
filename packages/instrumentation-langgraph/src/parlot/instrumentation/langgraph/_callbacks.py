"""LangChain / LangGraph callback handler → GenAI + Conversation Contract spans."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from opentelemetry.util.types import AttributeValue

from parlot.core.attrs import (
    ATTR_AGENT_FRAMEWORK,
    ATTR_AGENT_ROLE,
    ATTR_AGENT_STAGE,
    ATTR_AGENT_TOOL_IS_ERROR,
    ATTR_AGENT_TOOL_NAME,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_TOOL_NAME,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_USER_MESSAGE,
    GEN_AI_OP_CHAT,
    GEN_AI_OP_EXECUTE_TOOL,
    GEN_AI_OP_INVOKE_AGENT,
    GEN_AI_OP_INVOKE_WORKFLOW,
    SPAN_GEN_AI_INVOKE_AGENT,
    SPAN_GEN_AI_INVOKE_WORKFLOW,
    span_name_chat,
    span_name_execute_tool,
)
from parlot.instrumentation.langgraph.attrs import (
    ATTR_LG_GRAPH_NAME,
    ATTR_LG_NODE_NAME,
    ATTR_LG_RUN_ID,
    ATTR_LG_THREAD_ID,
)
from parlot.instrumentation.langgraph._session import (
    emit_turn,
    ensure_session,
    livekit_owns_session,
    thread_id_from_metadata,
)

logger = logging.getLogger("parlot.instrumentation.langgraph")

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover
    BaseCallbackHandler = object  # type: ignore[misc, assignment]


class ParlotLangGraphCallbackHandler(BaseCallbackHandler):
    """Emits GenAI spans for chain/LLM/tool events; owns session when standalone."""

    raise_error = False

    def __init__(
        self,
        tracer: Tracer,
        *,
        capture_content: bool = True,
    ) -> None:
        self._tracer = tracer
        self._capture_content = capture_content
        self._spans: dict[str, Span] = {}
        self._root_runs: set[str] = set()

    @property
    def ignore_chain(self) -> bool:
        return False

    @property
    def ignore_llm(self) -> bool:
        return False

    @property
    def ignore_agent(self) -> bool:
        return False

    def _run_key(self, run_id: UUID | None) -> str:
        return str(run_id) if run_id else ""

    def _start(
        self,
        name: str,
        run_id: UUID | None,
        *,
        attributes: dict[str, AttributeValue] | None = None,
        parent_run_id: UUID | None = None,
    ) -> Span | None:
        key = self._run_key(run_id)
        if not key:
            return None
        parent_ctx = None
        if parent_run_id is not None:
            parent = self._spans.get(self._run_key(parent_run_id))
            if parent is not None:
                parent_ctx = trace.set_span_in_context(parent)
        span = self._tracer.start_span(name, context=parent_ctx, attributes=attributes or {})
        self._spans[key] = span
        return span

    def _end(self, run_id: UUID | None, *, error: BaseException | None = None) -> None:
        key = self._run_key(run_id)
        span = self._spans.pop(key, None)
        if span is None:
            return
        if error is not None:
            span.set_status(Status(StatusCode.ERROR, str(error)[:500]))
            span.record_exception(error)
        else:
            span.set_status(Status(StatusCode.OK))
        span.end()

    def _thread_id(self, **kwargs: Any) -> str:
        metadata = kwargs.get("metadata") or {}
        tags = kwargs.get("tags")
        tid = thread_id_from_metadata(metadata if isinstance(metadata, dict) else {})
        if tid:
            return tid
        # LangGraph puts thread_id under metadata["thread_id"] or configurable
        cfg = kwargs.get("config")
        if isinstance(cfg, dict):
            configurable = cfg.get("configurable") or {}
            if isinstance(configurable, dict) and configurable.get("thread_id"):
                return str(configurable["thread_id"])
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and tag.startswith("thread_id:"):
                    return tag.split(":", 1)[1]
        return ""

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        serialized = serialized or {}
        chain_name = name or serialized.get("name") or serialized.get("id", ["chain"])[-1]
        thread_id = self._thread_id(metadata=metadata, tags=tags, **kwargs)
        state = ensure_session(thread_id) if thread_id or not livekit_owns_session() else None
        if state is None and not livekit_owns_session():
            state = ensure_session(thread_id or "")

        is_root = parent_run_id is None
        span_name = SPAN_GEN_AI_INVOKE_AGENT if is_root else SPAN_GEN_AI_INVOKE_WORKFLOW
        op = GEN_AI_OP_INVOKE_AGENT if is_root else GEN_AI_OP_INVOKE_WORKFLOW
        attrs: dict[str, AttributeValue] = {
            ATTR_AGENT_FRAMEWORK: "langgraph",
            ATTR_GEN_AI_OP_NAME: op,
            ATTR_AGENT_ROLE: "pipeline" if is_root else "pipeline",
            ATTR_AGENT_STAGE: "node" if not is_root else "turn",
            ATTR_LG_GRAPH_NAME: str(chain_name),
            ATTR_LG_RUN_ID: str(run_id),
        }
        if not is_root:
            attrs[ATTR_LG_NODE_NAME] = str(chain_name)
        if state is not None:
            attrs["session.id"] = state.session_id
            attrs[ATTR_LG_THREAD_ID] = state.thread_id
        elif thread_id:
            attrs[ATTR_LG_THREAD_ID] = thread_id

        self._start(
            span_name,
            run_id,
            attributes=attrs,
            parent_run_id=parent_run_id,
        )
        if is_root:
            self._root_runs.add(str(run_id))
            if state is not None and not livekit_owns_session():
                # One turn per root invoke when we own the session
                emit_turn(state, role="user")
                emit_turn(state, role="agent")

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._end(run_id)
        self._root_runs.discard(str(run_id))

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._end(run_id, error=error)
        self._root_runs.discard(str(run_id))

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        serialized = serialized or {}
        metadata = metadata or {}
        model = str(
            metadata.get("ls_model_name")
            or serialized.get("name")
            or metadata.get("model")
            or ""
        ).strip()
        provider = str(metadata.get("ls_provider") or "").strip()
        attrs: dict[str, AttributeValue] = {
            ATTR_AGENT_FRAMEWORK: "langgraph",
            ATTR_GEN_AI_OP_NAME: GEN_AI_OP_CHAT,
            ATTR_AGENT_ROLE: "llm",
            ATTR_AGENT_STAGE: "run",
            ATTR_LG_RUN_ID: str(run_id),
        }
        if model:
            attrs[ATTR_GEN_AI_MODEL] = model
        if provider:
            attrs[ATTR_GEN_AI_PROVIDER] = provider
        span = self._start(
            span_name_chat(model or None),
            run_id,
            attributes=attrs,
            parent_run_id=parent_run_id,
        )
        if span is not None and self._capture_content and prompts:
            span.add_event(
                EVENT_GEN_AI_USER_MESSAGE,
                {"content": prompts[-1][:4000]},
            )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        prompts: list[str] = []
        for batch in messages or []:
            for msg in batch:
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content:
                    prompts.append(content)
        self.on_llm_start(
            serialized,
            prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
            **kwargs,
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        span = self._spans.get(self._run_key(run_id))
        if span is not None:
            usage = _usage_from_llm_result(response)
            if usage.get("input"):
                span.set_attribute(ATTR_GEN_AI_IN_TOKENS, usage["input"])
            if usage.get("output"):
                span.set_attribute(ATTR_GEN_AI_OUT_TOKENS, usage["output"])
            if self._capture_content:
                text = _text_from_llm_result(response)
                if text:
                    span.add_event(
                        EVENT_GEN_AI_ASSISTANT_MESSAGE,
                        {"content": text[:4000]},
                    )
        self._end(run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._end(run_id, error=error)

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        serialized = serialized or {}
        tool_name = str(
            serialized.get("name") or kwargs.get("name") or "tool"
        ).strip() or "tool"
        attrs: dict[str, AttributeValue] = {
            ATTR_AGENT_FRAMEWORK: "langgraph",
            ATTR_GEN_AI_OP_NAME: GEN_AI_OP_EXECUTE_TOOL,
            ATTR_AGENT_ROLE: "tool",
            ATTR_AGENT_STAGE: "call",
            ATTR_AGENT_TOOL_NAME: tool_name,
            ATTR_GEN_AI_TOOL_NAME: tool_name,
            ATTR_LG_RUN_ID: str(run_id),
        }
        self._start(
            span_name_execute_tool(tool_name),
            run_id,
            attributes=attrs,
            parent_run_id=parent_run_id,
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._end(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        span = self._spans.get(self._run_key(run_id))
        if span is not None:
            span.set_attribute(ATTR_AGENT_TOOL_IS_ERROR, True)
        self._end(run_id, error=error)


def _usage_from_llm_result(response: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    llm_output = getattr(response, "llm_output", None) or {}
    if isinstance(llm_output, dict):
        token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if isinstance(token_usage, dict):
            for key, dest in (
                ("prompt_tokens", "input"),
                ("input_tokens", "input"),
                ("completion_tokens", "output"),
                ("output_tokens", "output"),
            ):
                if key in token_usage and dest not in out:
                    try:
                        out[dest] = int(token_usage[key])
                    except (TypeError, ValueError):
                        pass
    generations = getattr(response, "generations", None) or []
    for gen_list in generations:
        for gen in gen_list or []:
            msg = getattr(gen, "message", None)
            meta = getattr(msg, "usage_metadata", None) if msg is not None else None
            if isinstance(meta, dict):
                if "input_tokens" in meta and "input" not in out:
                    try:
                        out["input"] = int(meta["input_tokens"])
                    except (TypeError, ValueError):
                        pass
                if "output_tokens" in meta and "output" not in out:
                    try:
                        out["output"] = int(meta["output_tokens"])
                    except (TypeError, ValueError):
                        pass
    return out


def _text_from_llm_result(response: Any) -> str:
    generations = getattr(response, "generations", None) or []
    parts: list[str] = []
    for gen_list in generations:
        for gen in gen_list or []:
            text = getattr(gen, "text", None)
            if text:
                parts.append(str(text))
                continue
            msg = getattr(gen, "message", None)
            content = getattr(msg, "content", None) if msg is not None else None
            if isinstance(content, str):
                parts.append(content)
    return "\n".join(parts)
