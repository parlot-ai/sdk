"""
AgentSession auto-patcher for LiveKit instrumentation.

Event subscriptions live in ``_events.py`` (semantic/commit layer). Span
processing remains in ``LiveKitGenAIProcessor`` (pipeline/waterfall layer).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._processor import LiveKitGenAIProcessor

logger = logging.getLogger("parlot.instrumentation.livekit")


def _patch_agent_session(processor: "LiveKitGenAIProcessor", tracer) -> None:
    """Monkey-patch ``AgentSession.__init__`` to auto-install event hooks."""
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
            from ._events import install_session_hooks

            install_session_hooks(self, processor, tracer)
        except Exception:
            logger.debug("Could not auto-install session hooks", exc_info=True)

    AgentSession.__init__ = _patched_init
    AgentSession._parlot_patched = True
    logger.debug("Patched AgentSession.__init__ for Parlot event + close hooks")
