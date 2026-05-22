"""parlot-instrumentation-livekit: OTel instrumentation for LiveKit Agents."""

from ._auto import configure
from ._hooks import install_handoff_hook
from ._processor import LiveKitGenAIProcessor

__all__ = [
    "configure",
    "install_handoff_hook",
    "LiveKitGenAIProcessor",
]
