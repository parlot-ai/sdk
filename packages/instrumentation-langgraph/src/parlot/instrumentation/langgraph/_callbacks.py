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
    ATTR_GEN_AI_CONVERSATION_ID,
    ATTR_GEN_AI_IN_TOKENS,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    ATTR_GEN_AI_OUT_TOKENS,
    ATTR_GEN_AI_PROVIDER,
    ATTR_GEN_AI_TOOL_NAME,
    ATTR_SESSION_CONVERSATION_ID,
    ATTR_SESSION_ID,
    ATTR_TOOL_INPUT_PAYLOAD,
    ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
    ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW,
    ATTR_TURN_INDEX,
    EVENT_GEN_AI_ASSISTANT_MESSAGE,
    EVENT_GEN_AI_TOOL_MESSAGE,
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
from parlot.core.session import get_active_session
from parlot.instrumentation.langgraph.attrs import (
    ATTR_LG_GRAPH_NAME,
    ATTR_LG_NODE_NAME,
    ATTR_LG_RUN_ID,
    ATTR_LG_THREAD_ID,
)
from parlot.instrumentation.langgraph._session import (
    _LangGraphSessionState,
    emit_turn,
    ensure_session,
    livekit_owns_session,
    thread_id_from_metadata,
)


def _message_content(msg: Any) -> str:
    if msg is None:
        return ""
    if isinstance(msg, dict):
        content = msg.get("content")
    else:
        content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return str(content or "").strip()


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        role = str(msg.get("role") or msg.get("type") or "").lower()
        if role:
            return role
    role = str(getattr(msg, "type", None) or getattr(msg, "role", "") or "").lower()
    if role:
        return role
    name = msg.__class__.__name__ if msg is not None else ""
    if name == "HumanMessage":
        return "human"
    if name == "AIMessage":
        return "ai"
    if name == "ToolMessage":
        return "tool"
    return ""


def _messages_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            return messages
    if isinstance(payload, list):
        return payload
    return []


def _last_message_text(messages: list[Any], *, roles: set[str]) -> str:
    for msg in reversed(messages):
        if _message_role(msg) in roles:
            text = _message_content(msg)
            if text:
                return text
    return ""

logger = logging.getLogger("parlot.instrumentation.langgraph")

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError:  # pragma: no cover
    BaseCallbackHandler = object  # type: ignore[misc, assignment]


class ParlotLangGraphCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that emits Parlot GenAI spans.

    Translates LangGraph / LangChain execution events (LLM starts/ends, tool
    invocations, chain runs) into OpenTelemetry GenAI spans
    (``invoke_agent``, ``invoke_workflow``, ``chat``, ``execute_tool``).

    ``configure()`` registers this handler via LangChain configuration hooks,
    so manual ``callbacks=[...]`` attachment is not required. When LiveKit
    owns the active session, contract spans are suppressed and GenAI ops nest
    under the current OTel context.
    """

    raise_error = False

    def __init__(
        self,
        tracer: Tracer,
        *,
        capture_genai_content: bool = True,
    ) -> None:
        self._tracer = tracer
        self._capture_genai_content = capture_genai_content
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

    def _active_langgraph_state(self) -> _LangGraphSessionState | None:
        state = get_active_session()
        if isinstance(state, _LangGraphSessionState):
            return state
        return None

    def _contract_attrs(
        self, state: _LangGraphSessionState | None
    ) -> dict[str, AttributeValue]:
        """Session/turn keys required by collector operational ingest."""
        if state is None:
            return {}
        turn_index = state.open_agent_turn_index or state.turn_count
        attrs: dict[str, AttributeValue] = {
            ATTR_SESSION_ID: state.session_id,
            ATTR_SESSION_CONVERSATION_ID: state.conversation_id,
            ATTR_GEN_AI_CONVERSATION_ID: state.conversation_id,
            ATTR_LG_THREAD_ID: state.thread_id,
        }
        if turn_index > 0:
            attrs[ATTR_TURN_INDEX] = turn_index
        return attrs

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
        if is_root:
            self._root_runs.add(str(run_id))
            if state is not None and not livekit_owns_session():
                user_text = _last_message_text(
                    _messages_from_payload(inputs),
                    roles={"human", "user"},
                )
                user_idx = emit_turn(
                    state,
                    role="user",
                    utterance_text=user_text,
                )
                state.open_agent_turn_index = user_idx + 1
        attrs.update(self._contract_attrs(state))

        self._start(
            span_name,
            run_id,
            attributes=attrs,
            parent_run_id=parent_run_id,
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        key = str(run_id)
        if key in self._root_runs:
            state = self._active_langgraph_state()
            if state is not None and not livekit_owns_session():
                agent_text = _last_message_text(
                    _messages_from_payload(outputs),
                    roles={"ai", "assistant"},
                )
                emit_turn(
                    state,
                    role="agent",
                    turn_index=state.open_agent_turn_index,
                    utterance_text=agent_text,
                )
                state.open_agent_turn_index = None
        self._end(run_id)
        self._root_runs.discard(key)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        key = str(run_id)
        if key in self._root_runs:
            state = self._active_langgraph_state()
            if state is not None:
                state.open_agent_turn_index = None
        self._end(run_id, error=error)
        self._root_runs.discard(key)

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
            ATTR_AGENT_STAGE: "node",
            ATTR_LG_RUN_ID: str(run_id),
        }
        if model:
            attrs[ATTR_GEN_AI_MODEL] = model
        if provider:
            attrs[ATTR_GEN_AI_PROVIDER] = provider
        attrs.update(self._contract_attrs(self._active_langgraph_state()))
        span = self._start(
            span_name_chat(model or None),
            run_id,
            attributes=attrs,
            parent_run_id=parent_run_id,
        )
        if span is not None and self._capture_genai_content and prompts:
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
            if self._capture_genai_content:
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
        attrs.update(self._contract_attrs(self._active_langgraph_state()))
        span = self._start(
            span_name_execute_tool(tool_name),
            run_id,
            attributes=attrs,
            parent_run_id=parent_run_id,
        )
        if span is not None and self._capture_genai_content:
            payload = ""
            if inputs is not None:
                try:
                    import json

                    payload = json.dumps(inputs, default=str)
                except Exception:
                    payload = str(inputs)
            elif input_str:
                payload = str(input_str)
            if payload:
                trimmed = payload[:8192]
                span.set_attribute(ATTR_TOOL_INPUT_PAYLOAD, trimmed)
                span.set_attribute(
                    ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
                    trimmed[:512],
                )
                span.add_event(
                    EVENT_GEN_AI_TOOL_MESSAGE,
                    {"content": trimmed[:4000], "role": "tool_input"},
                )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        span = self._spans.get(self._run_key(run_id))
        if span is not None and self._capture_genai_content and output is not None:
            text = str(output)
            if text:
                preview = text[:512]
                span.set_attribute(ATTR_TOOL_OUTPUT_PAYLOAD_PREVIEW, preview)
                span.add_event(
                    EVENT_GEN_AI_TOOL_MESSAGE,
                    {"content": text[:4000], "role": "tool"},
                )
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
