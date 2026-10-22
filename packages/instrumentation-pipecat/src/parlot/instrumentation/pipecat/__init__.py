"""parlot-instrumentation-pipecat: OTel instrumentation for Pipecat agents."""

from parlot.core import (
    add_platform_ref,
    human_escalation,
    record_human_rep,
    set_session_attribute,
    set_session_metadata,
    stamp_platform_refs,
)

from ._auto import close_session, parlotize
from ._processor import PipecatGenAIProcessor

__all__ = [
    "parlotize",
    "close_session",
    "PipecatGenAIProcessor",
    "add_platform_ref",
    "human_escalation",
    "record_human_rep",
    "set_session_attribute",
    "set_session_metadata",
    "stamp_platform_refs",
]
