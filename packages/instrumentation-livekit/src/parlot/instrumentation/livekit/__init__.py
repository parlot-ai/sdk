"""parlot-instrumentation-livekit: OTel instrumentation for LiveKit Agents."""

from ._auto import configure
from ._hooks import install_handoff_hook
from ._platform_refs import register_job_context
from ._processor import LiveKitGenAIProcessor

__all__ = [
    "configure",
    "register_job_context",
    "install_handoff_hook",
    "LiveKitGenAIProcessor",
]
