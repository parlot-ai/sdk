"""parlot-instrumentation-livekit: OTel instrumentation for LiveKit Agents."""

from parlot.core import (
    add_platform_ref,
    human_escalation,
    record_human_rep,
    set_session_attribute,
    set_session_metadata,
    stamp_platform_refs,
)

from ._auto import parlotize
from ._events import install_session_hooks
from ._processor import LiveKitGenAIProcessor

__all__ = [
    "parlotize",
    "install_session_hooks",
    "LiveKitGenAIProcessor",
    "add_platform_ref",
    "human_escalation",
    "record_human_rep",
    "set_session_attribute",
    "set_session_metadata",
    "stamp_platform_refs",
]
