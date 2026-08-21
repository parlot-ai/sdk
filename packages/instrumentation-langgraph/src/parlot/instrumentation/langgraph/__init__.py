"""parlot-instrumentation-langgraph: OTel instrumentation for LangGraph / LangChain agents."""

from parlot.core import (
    add_platform_ref,
    human_escalation,
    record_human_rep,
    set_session_attribute,
    set_session_metadata,
    stamp_platform_refs,
)

from ._auto import close_session, configure
from ._callbacks import ParlotLangGraphCallbackHandler

__all__ = [
    "configure",
    "close_session",
    "ParlotLangGraphCallbackHandler",
    "add_platform_ref",
    "human_escalation",
    "record_human_rep",
    "set_session_attribute",
    "set_session_metadata",
    "stamp_platform_refs",
]
