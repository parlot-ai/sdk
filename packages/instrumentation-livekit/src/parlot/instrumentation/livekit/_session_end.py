"""LiveKit ``on_session_end`` hook: SessionReport + recording anchor after RecorderIO stops."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("parlot.instrumentation.livekit")


async def handle_session_end(ctx: Any) -> None:
    """Build SessionReport after recording finishes and finalize deferred session teardown."""
    job = getattr(ctx, "job", None)
    job_id = str(getattr(job, "id", "") or "")
    if not job_id:
        return

    report = None
    make_report = getattr(ctx, "make_session_report", None)
    if callable(make_report):
        try:
            report = make_report()
        except Exception:
            logger.debug(
                "parlot: make_session_report failed in on_session_end",
                exc_info=True,
            )
            report = getattr(ctx, "session_report", None)
    else:
        report = getattr(ctx, "session_report", None)

    logger.debug(f"session_end: {report}")
    from ._session import finalize_deferred_session_end

    finalize_deferred_session_end(job_id=job_id, report=report)


class _ComposedSessionEnd:
    """Pickle-friendly ``on_session_end`` that runs Parlot then an optional user handler."""

    __slots__ = ("user_fn",)

    def __init__(self, user_fn: Callable[[Any], Awaitable[None]] | None) -> None:
        self.user_fn = user_fn

    async def __call__(self, ctx: Any) -> None:
        try:
            await handle_session_end(ctx)
        except Exception:
            logger.debug("parlot: handle_session_end failed", exc_info=True)
        if self.user_fn is not None:
            await self.user_fn(ctx)


def patch_agent_server_run() -> None:
    """Compose Parlot's session-end handler onto ``AgentServer._session_end_fnc`` before ``run``."""
    try:
        from livekit.agents import AgentServer
    except ImportError:
        logger.debug("livekit-agents not importable; AgentServer.run not patched")
        return

    if getattr(AgentServer, "_parlot_run_patched", False):
        return

    original_run = AgentServer.run

    async def patched_run(self, *, devmode: bool = False, unregistered: bool = False):
        if not getattr(self, "_parlot_session_end_wrapped", False):
            original_end = self._session_end_fnc
            self._session_end_fnc = _ComposedSessionEnd(original_end)
            self._parlot_session_end_wrapped = True
        return await original_run(self, devmode=devmode, unregistered=unregistered)

    AgentServer.run = patched_run
    AgentServer._parlot_run_patched = True
    logger.debug("Patched AgentServer.run for on_session_end recording anchor")
