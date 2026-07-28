"""parlot-core: shared semantic conventions, base processor, and utilities."""

from .attrs import *  # noqa: F401, F403 — re-export all attribute constants
from .diagnostics import (
    diagnostics_enabled,
    init_diagnostics,
    record_diagnostic,
    shutdown_diagnostics,
)
from .escalation import human_escalation, record_human_rep
from .metadata import set_session_attribute, set_session_metadata
from .platform_refs import add_platform_ref, stamp_platform_refs
from .processor import ParlotBaseProcessor, assert_sync_span_processors
from .intent import derive_intent
from .sdk_version import resolve_parlot_sdk_version, stamp_session_sdk_version
from .session import SessionState
from .topology import SessionTopology

__all__ = [
    "ParlotBaseProcessor",
    "assert_sync_span_processors",
    "SessionState",
    "SessionTopology",
    "add_platform_ref",
    "derive_intent",
    "diagnostics_enabled",
    "human_escalation",
    "init_diagnostics",
    "record_diagnostic",
    "record_human_rep",
    "resolve_parlot_sdk_version",
    "set_session_attribute",
    "set_session_metadata",
    "shutdown_diagnostics",
    "stamp_platform_refs",
    "stamp_session_sdk_version",
]
