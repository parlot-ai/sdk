"""
Handoff and close hooks and AgentSession auto-patcher for LiveKit instrumentation.

Because livekit-agents 1.5.x does not emit a dedicated handoff span (the source
has a TODO for it), the correct approach is to hook into AgentSession's
``conversation_item_added`` event and emit our own span.
"""

from __future__ import annotations

import logging

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_CREATED_AT,
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_ITEM_ID,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_GEN_AI_OP_NAME,
)

logger = logging.getLogger("parlot.instrumentation.livekit")


def install_handoff_hook(session, tracer) -> None:
    """Subscribe to AgentSession conversation events and emit a
    ``lk.agent_handoff`` span for each AgentHandoff item.

    This is called automatically by ``configure()`` when AgentSession is
    constructed. You only need to call it manually if you are managing the
    ``TracerProvider`` yourself (BYO provider path).

    Args:
        session: A ``livekit.agents.AgentSession`` instance.
        tracer:  An ``opentelemetry.trace.Tracer`` to emit spans with.
    """

    @session.on("conversation_item_added")
    def _on_item_added(ev) -> None:
        item = ev.item
        if item.type != "agent_handoff":
            return

        with tracer.start_as_current_span("lk.agent_handoff") as span:
            if item.old_agent_id:
                span.set_attribute(ATTR_AGENT_TRANSFER_FROM, str(item.old_agent_id))
            span.set_attribute(ATTR_AGENT_TRANSFER_TO, str(item.new_agent_id))
            span.set_attribute(ATTR_GEN_AI_OP_NAME, "agent_handoff")
            span.set_attribute(ATTR_AGENT_TRANSFER_ITEM_ID, str(item.id))
            span.set_attribute(ATTR_AGENT_TRANSFER_CREATED_AT, float(item.created_at))
            # Transition latency (dead air) is computed by LiveKitGenAIProcessor
            # when it sees the next llm_request_run span.


def install_close_hook(session) -> None:
    """Emit ``parlot.session.close`` from the LiveKit session close event."""

    @session.on("close")
    def _on_close(ev) -> None:
        from ._session import emit_parlot_session_close_span, get_job_bootstrap

        bootstrap = get_job_bootstrap()
        if bootstrap is None or bootstrap.close_span_done:
            return
        reason = str(getattr(ev, "reason", "unknown"))
        error = getattr(ev, "error", None)
        emit_parlot_session_close_span(
            bootstrap,
            close_reason=reason,
            close_error=str(error) if error else None,
        )
        bootstrap.close_span_done = True


def _patch_agent_session(tracer) -> None:
    """Monkey-patch ``AgentSession.__init__`` to auto-install the handoff hook.

    Called once by ``configure()``. Safe to call multiple times — subsequent
    calls are no-ops if the patch is already applied.
    """
    try:
        import livekit.agents as _lk_agents
    except ImportError:
        logger.debug("livekit-agents not importable; skipping AgentSession patch")
        return

    AgentSession = getattr(_lk_agents, "AgentSession", None)
    if AgentSession is None:
        return

    if getattr(AgentSession, "_parlot_patched", False):
        return

    _original_init = AgentSession.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        try:
            install_handoff_hook(self, tracer)
            install_close_hook(self)
        except Exception:
            logger.debug("Could not auto-install session hooks", exc_info=True)

    AgentSession.__init__ = _patched_init
    AgentSession._parlot_patched = True
    logger.debug("Patched AgentSession.__init__ for auto handoff + close hooks")
