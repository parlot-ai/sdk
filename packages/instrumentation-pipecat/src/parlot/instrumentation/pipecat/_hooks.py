"""Patch Pipecat PipelineWorker / aggregators so tracing + turns stay on after parlotize()."""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any

logger = logging.getLogger("parlot.instrumentation.pipecat")

_patched = False
_tool_patched = False
_aggregator_patched = False
_latency_patched = False


def install_pipeline_worker_hooks() -> None:
    """Ensure PipelineWorker enables tracing, turn tracking, and metrics."""
    global _patched
    if _patched:
        return

    try:
        from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    except ImportError:
        logger.warning(
            "parlot: pipecat PipelineWorker not importable; "
            "enable_tracing=True must be set manually"
        )
        return

    original_init = PipelineWorker.__init__
    init_params = inspect.signature(original_init).parameters
    supports_turn_tracking = "enable_turn_tracking" in init_params

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        params = kwargs.get("params")
        if params is None and len(args) >= 2 and isinstance(args[1], PipelineParams):
            params = args[1]
        if params is None:
            kwargs["params"] = PipelineParams(
                enable_metrics=True,
                enable_usage_metrics=True,
            )
        else:
            for flag in ("enable_metrics", "enable_usage_metrics"):
                if hasattr(params, flag) and not getattr(params, flag):
                    try:
                        setattr(params, flag, True)
                    except Exception:
                        pass

        kwargs.setdefault("enable_tracing", True)
        if supports_turn_tracking:
            kwargs.setdefault("enable_turn_tracking", True)

        original_init(self, *args, **kwargs)
        _bind_latency_observer(self)

    PipelineWorker.__init__ = patched_init  # type: ignore[method-assign]
    _patched = True
    logger.debug("parlot: patched Pipecat PipelineWorker for tracing defaults")


def _bind_latency_observer(worker: Any) -> None:
    """Attach Parlot handler to PipelineWorker's UserBotLatencyObserver."""
    observer = getattr(worker, "_user_bot_latency_observer", None)
    if observer is None or getattr(observer, "_parlot_latency_bound", False):
        return
    from ._turn_events import handle_latency_measured

    observer.add_event_handler("on_latency_measured", handle_latency_measured)
    observer._parlot_latency_bound = True


def install_latency_observer_hooks() -> None:
    """Also patch ``UserBotLatencyObserver.__init__`` for manually added observers."""
    global _latency_patched
    if _latency_patched:
        return

    try:
        from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
    except ImportError:
        return

    if getattr(UserBotLatencyObserver.__init__, "_parlot_latency_wrapped", False):
        _latency_patched = True
        return

    from ._turn_events import handle_latency_measured

    original_init = UserBotLatencyObserver.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if getattr(self, "_parlot_latency_bound", False):
            return
        self.add_event_handler("on_latency_measured", handle_latency_measured)
        self._parlot_latency_bound = True

    patched_init._parlot_latency_wrapped = True  # type: ignore[attr-defined]
    UserBotLatencyObserver.__init__ = patched_init  # type: ignore[method-assign]
    _latency_patched = True
    logger.debug("parlot: patched UserBotLatencyObserver for e2e latency")


def install_tool_call_hooks() -> None:
    """Wrap ``LLMService._run_function_call`` to emit ``execute_tool`` spans.

    OpenAI/Deepgram Pipecat paths do not create ``llm_tool_call`` OTEL spans
    (those exist for Gemini Live). Without this, tool calls never appear on
    the Parlot timeline.
    """
    global _tool_patched
    if _tool_patched:
        return

    try:
        from pipecat.services.llm_service import LLMService
    except ImportError:
        return

    original = LLMService._run_function_call
    if getattr(original, "_parlot_wrapped", False):
        _tool_patched = True
        return

    async def _patched(self: Any, runner_item: Any) -> Any:
        from parlot.core.attrs import (
            ATTR_AGENT_ROLE,
            ATTR_AGENT_STAGE,
            ATTR_AGENT_TOOL_NAME,
            ATTR_GEN_AI_AGENT_ID,
            ATTR_GEN_AI_AGENT_NAME,
            ATTR_GEN_AI_OP_NAME,
            ATTR_GEN_AI_TOOL_CALL_ARGUMENTS,
            ATTR_GEN_AI_TOOL_NAME,
            ATTR_SESSION_AGENT_ID,
            ATTR_SESSION_CONVERSATION_ID,
            ATTR_SESSION_ID,
            ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
            ATTR_TURN_INDEX,
            GEN_AI_OP_EXECUTE_TOOL,
            span_name_execute_tool,
        )

        from ._platform_refs import stamp_pipecat_platform_refs
        from ._session import (
            allocate_agent_turn_index,
            any_open_session,
            configured_agent_id,
            get_tracer,
        )

        tool_name = str(getattr(runner_item, "function_name", None) or "tool")
        tracer = get_tracer()
        if tracer is None:
            return await original(self, runner_item)

        state = any_open_session()
        span = tracer.start_span(span_name_execute_tool(tool_name))
        try:
            # Minted GenAI spans skip processor enrichment (passthrough) — stamp
            # the full contract here so timeline Tool/Agent + topology work.
            span.set_attribute(ATTR_GEN_AI_OP_NAME, GEN_AI_OP_EXECUTE_TOOL)
            span.set_attribute(ATTR_GEN_AI_TOOL_NAME, tool_name)
            span.set_attribute(ATTR_AGENT_TOOL_NAME, tool_name)
            span.set_attribute(ATTR_AGENT_ROLE, "tool")
            span.set_attribute(ATTR_AGENT_STAGE, "call")
            agent_id = configured_agent_id()
            if agent_id:
                span.set_attribute(ATTR_GEN_AI_AGENT_ID, agent_id)
                span.set_attribute(ATTR_GEN_AI_AGENT_NAME, agent_id)
                span.set_attribute(ATTR_SESSION_AGENT_ID, agent_id)
            args = getattr(runner_item, "arguments", None)
            if args is not None:
                try:
                    raw = args if isinstance(args, str) else json.dumps(args)
                except Exception:
                    raw = str(args)
                clipped = raw[:4096]
                span.set_attribute(ATTR_GEN_AI_TOOL_CALL_ARGUMENTS, clipped)
                span.set_attribute(ATTR_TOOL_INPUT_PAYLOAD_PREVIEW, clipped[:512])
            if state is not None:
                span.set_attribute(ATTR_SESSION_ID, state.session_id)
                span.set_attribute(
                    ATTR_SESSION_CONVERSATION_ID, state.conversation_id
                )
                turn_idx = allocate_agent_turn_index(state)
                span.set_attribute(ATTR_TURN_INDEX, turn_idx)
                stamp_pipecat_platform_refs(
                    span, conversation_id=state.conversation_id
                )
            return await original(self, runner_item)
        except Exception as exc:
            try:
                span.record_exception(exc)
            except Exception:
                pass
            raise
        finally:
            span.end()

    _patched._parlot_wrapped = True  # type: ignore[attr-defined]
    LLMService._run_function_call = _patched  # type: ignore[method-assign]
    _tool_patched = True
    logger.debug("parlot: patched LLMService._run_function_call for tool spans")


def bind_user_aggregator(user_aggregator: Any) -> bool:
    """Attach Parlot turn handlers to an ``LLMUserAggregator`` (idempotent).

    Returns True if handlers were newly bound.
    """
    if user_aggregator is None:
        return False
    if getattr(user_aggregator, "_parlot_turn_handlers", False):
        return False
    from ._turn_events import (
        handle_user_turn_message_added,
        handle_user_turn_started,
        handle_user_turn_stopped,
    )

    user_aggregator.add_event_handler("on_user_turn_started", handle_user_turn_started)
    user_aggregator.add_event_handler("on_user_turn_stopped", handle_user_turn_stopped)
    user_aggregator.add_event_handler(
        "on_user_turn_message_added", handle_user_turn_message_added
    )
    user_aggregator._parlot_turn_handlers = True
    return True


def bind_assistant_aggregator(assistant_aggregator: Any) -> bool:
    """Attach Parlot turn handlers to an ``LLMAssistantAggregator`` (idempotent).

    Returns True if handlers were newly bound.
    """
    if assistant_aggregator is None:
        return False
    if getattr(assistant_aggregator, "_parlot_turn_handlers", False):
        return False
    from ._turn_events import (
        handle_assistant_turn_started,
        handle_assistant_turn_stopped,
    )

    assistant_aggregator.add_event_handler(
        "on_assistant_turn_started", handle_assistant_turn_started
    )
    assistant_aggregator.add_event_handler(
        "on_assistant_turn_stopped", handle_assistant_turn_stopped
    )
    assistant_aggregator._parlot_turn_handlers = True
    return True


def attach_aggregators(
    user_aggregator: Any = None,
    assistant_aggregator: Any = None,
) -> None:
    """Bind Parlot turn handlers onto existing context aggregators.

    Prefer calling ``parlotize()`` before constructing aggregators so the
    ``__init__`` patch auto-wires them. Use this when aggregators already
    exist (built before ``parlotize``, or handed in by a framework).

    Idempotent — safe to call more than once on the same instances.
    """
    bind_user_aggregator(user_aggregator)
    bind_assistant_aggregator(assistant_aggregator)


def install_aggregator_turn_hooks() -> None:
    """Wire Parlot turn minting onto LLM context aggregators.

    ``parlot.turn`` is minted from committed aggregator transcripts
    (``on_user_turn_stopped`` / ``on_assistant_turn_stopped`` /
    ``on_user_turn_message_added``), not from OTEL STT/native-turn spans.
    Bots must use ``LLMContextAggregatorPair`` with the assistant aggregator
    after ``transport.output()``.
    """
    global _aggregator_patched
    if _aggregator_patched:
        return

    try:
        from pipecat.processors.aggregators.llm_response_universal import (
            LLMAssistantAggregator,
            LLMUserAggregator,
        )
    except ImportError:
        logger.warning(
            "parlot: Pipecat LLMContextAggregator classes not importable; "
            "parlot.turn will not be minted from aggregator events"
        )
        return

    if not getattr(LLMUserAggregator.__init__, "_parlot_turn_wrapped", False):
        original_user_init = LLMUserAggregator.__init__

        def patched_user_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_user_init(self, *args, **kwargs)
            bind_user_aggregator(self)

        patched_user_init._parlot_turn_wrapped = True  # type: ignore[attr-defined]
        LLMUserAggregator.__init__ = patched_user_init  # type: ignore[method-assign]

    if not getattr(LLMAssistantAggregator.__init__, "_parlot_turn_wrapped", False):
        original_asst_init = LLMAssistantAggregator.__init__

        def patched_asst_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_asst_init(self, *args, **kwargs)
            bind_assistant_aggregator(self)

        patched_asst_init._parlot_turn_wrapped = True  # type: ignore[attr-defined]
        LLMAssistantAggregator.__init__ = patched_asst_init  # type: ignore[method-assign]

    _aggregator_patched = True
    logger.debug("parlot: patched LLM context aggregators for turn events")
