"""Register / uninstall the global LangChain configure hook."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("parlot.instrumentation.langgraph")

_handler_var: ContextVar[Any] = ContextVar("parlot_langgraph_handler", default=None)
_hook_registered = False


def install_configure_hook(handler: Any) -> None:
    """Register ``handler`` so every LangChain callback manager inherits it."""
    global _hook_registered
    _handler_var.set(handler)
    if _hook_registered:
        return
    try:
        from langchain_core.tracers.context import register_configure_hook
    except ImportError:
        logger.warning(
            "langchain_core not importable; Parlot LangGraph hooks not registered"
        )
        return

    register_configure_hook(
        _handler_var,
        inheritable=True,
    )
    _hook_registered = True
    logger.debug("Registered Parlot LangGraph configure hook")


def get_handler() -> Any:
    return _handler_var.get()
