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
from ._hooks import attach_aggregators
from ._processor import PipecatGenAIProcessor
from ._recording import ParlotRecordingProcessor
from parlot.core import stamp_external_recording

__all__ = [
    "parlotize",
    "attach_aggregators",
    "close_session",
    "PipecatGenAIProcessor",
    "ParlotRecordingProcessor",
    "stamp_external_recording",
    "add_platform_ref",
    "human_escalation",
    "record_human_rep",
    "set_session_attribute",
    "set_session_metadata",
    "stamp_platform_refs",
]
