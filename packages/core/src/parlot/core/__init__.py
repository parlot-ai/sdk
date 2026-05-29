"""parlot-core: shared semantic conventions, base processor, and utilities."""

from .attrs import *  # noqa: F401, F403 — re-export all attribute constants
from .platform_refs import stamp_platform_refs
from .processor import ParlotBaseProcessor, assert_sync_span_processors
from .session import SessionState

__all__ = [
    "ParlotBaseProcessor",
    "assert_sync_span_processors",
    "SessionState",
    "stamp_platform_refs",
]
