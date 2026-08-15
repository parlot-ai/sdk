"""Shared ``configure()`` keyword surface for instrumentation packages.

All adapter ``configure()`` entrypoints are keyword-only so the shape can
evolve without breaking positional call sites.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class ConfigureProtocol(Protocol):
    """Common kwargs every adapter ``configure()`` must accept.

    Framework packages may add extra keyword-only parameters (e.g. LiveKit
    ``record=`` / ``auto_escalate_sip=``).
    """

    def __call__(
        self,
        *,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        capture_genai_content: Optional[bool] = None,
        service_name: Optional[str] = None,
        tracer_provider: Any = None,
        agent_id: Optional[str] = None,
        version: Optional[str] = None,
        **kwargs: Any,
    ) -> None: ...
