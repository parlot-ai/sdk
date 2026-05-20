"""
Auto-configuration helpers for parlot-instrumentation-livekit.

``configure()`` is the main entry point. It:
  1. Builds a TracerProvider from env vars (or accepts a BYO provider).
  2. Registers it with livekit.agents.telemetry.
  3. Patches the LiveKit job process to auto-register job context
     (room SID, job ID) before the user's entrypoint runs.
  4. Patches AgentSession to auto-install the handoff hook.

Environment variables:
  PARLOT_ENDPOINT         OTLP HTTP endpoint (e.g. http://localhost:4318)
  PARLOT_API_KEY          API key sent as Bearer token in the Authorization header
  PARLOT_CAPTURE_CONTENT  "false" to disable prompt/response capture (default: true)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("parlot.instrumentation.livekit")

_configured = False


def configure(
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    capture_content: Optional[bool] = None,
    prices: Optional[dict] = None,
    tracer_provider=None,
) -> None:
    """Configure Parlot instrumentation for a LiveKit Agents application.

    Call this once at the top of your agent file, before any LiveKit imports
    if possible::

        from parlot.instrumentation.livekit import configure
        configure()

        import livekit.agents as agents
        # ... rest of agent code unchanged

    All arguments are optional; configuration falls back to environment
    variables when not provided.

    Args:
        endpoint: OTLP HTTP endpoint. Falls back to ``PARLOT_ENDPOINT``.
        api_key: API key for the Parlot backend. Falls back to ``PARLOT_API_KEY``.
        capture_content: Whether to capture prompt/response text as span events.
            Falls back to ``PARLOT_CAPTURE_CONTENT`` env var (default ``True``).
        prices: Custom model price table passed to ``LiveKitGenAIProcessor``.
            Keys are model name prefixes; values are (input_$/M, output_$/M).
        tracer_provider: Supply your own pre-built ``TracerProvider`` and skip
            auto-construction. The provider is still registered with LiveKit.
            Use this when you need full control (e.g. adding extra processors,
            using a different exporter).
    """
    global _configured
    if _configured:
        logger.debug("parlot.instrumentation.livekit already configured — skipping")
        return

    resolved_endpoint = endpoint or os.environ.get("PARLOT_ENDPOINT", "")
    resolved_api_key  = api_key  or os.environ.get("PARLOT_API_KEY", "")

    if capture_content is None:
        env_val = os.environ.get("PARLOT_CAPTURE_CONTENT", "").lower()
        capture_content = env_val not in ("false", "0", "no")

    if tracer_provider is None:
        if not resolved_endpoint:
            raise ValueError(
                "No OTLP endpoint configured. Pass endpoint= or set the "
                "PARLOT_ENDPOINT environment variable."
            )
        tracer_provider = _build_provider(
            endpoint=resolved_endpoint,
            api_key=resolved_api_key,
            capture_content=capture_content,
            prices=prices,
        )

    _register_with_livekit(tracer_provider)
    _patch_job_proc_entrypoint()
    _patch_job_context_connect()
    _patch_agent_session_with_tracer(tracer_provider)

    _configured = True
    logger.debug("parlot-instrumentation-livekit configured (endpoint=%s)", resolved_endpoint)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_provider(
    endpoint: str,
    api_key: str,
    capture_content: bool,
    prices: Optional[dict],
):
    """Build a TracerProvider with LiveKitGenAIProcessor + OTLP exporter."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from opentelemetry import metrics as otel_metrics

    from ._export import QuietOTLPSpanExporter
    from ._metrics import ParlotMetricsRecorder, build_meter_provider
    from ._processor import LiveKitGenAIProcessor
    from ._turn_trace_export import TurnTraceRemappingExporter

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
    otlp_exporter = OTLPSpanExporter(endpoint=trace_endpoint, headers=headers)

    processor = LiveKitGenAIProcessor(
        capture_content=capture_content,
        prices=prices,
    )

    remapping_exporter = TurnTraceRemappingExporter(otlp_exporter, processor)
    exporter = QuietOTLPSpanExporter(
        remapping_exporter,
        endpoint_label=trace_endpoint,
    )

    provider = TracerProvider()
    provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    meter_provider = build_meter_provider(endpoint, headers)
    otel_metrics.set_meter_provider(meter_provider)
    processor.set_tracer(provider.get_tracer("parlot.instrumentation.livekit"))
    processor.set_metrics(ParlotMetricsRecorder(meter_provider))

    return provider


def _register_with_livekit(provider) -> None:
    """Hand the provider to livekit.agents.telemetry."""
    try:
        from livekit.agents import telemetry as _lk_telemetry
        _lk_telemetry.set_tracer_provider(provider)
        logger.debug("Registered TracerProvider with livekit.agents.telemetry")
    except ImportError:
        logger.debug(
            "livekit-agents not importable; provider NOT registered with LiveKit. "
            "Install livekit-agents or register the provider manually."
        )


# Module-level wrapt decorator (pickle-safe identity; see _patch_job_proc_entrypoint).
try:
    import wrapt

    @wrapt.decorator
    async def _parlot_entrypoint_wrapper(wrapped, instance, args, kwargs):
        from ._platform_refs import register_livekit_job_context_from_ctx

        ctx = args[0] if args else kwargs.get("ctx")
        if ctx is not None:
            try:
                await register_livekit_job_context_from_ctx(ctx)
            except Exception:
                logger.debug("Could not auto-register job context", exc_info=True)
        return await wrapped(*args, **kwargs)

except ImportError:  # pragma: no cover - configure() requires wrapt via pyproject
    wrapt = None  # type: ignore[assignment]
    _parlot_entrypoint_wrapper = None  # type: ignore[assignment,misc]


def _wrap_entrypoint(entrypoint_fnc):
    """Wrap the user entrypoint with the module-level Parlot decorator."""
    if _parlot_entrypoint_wrapper is None:
        raise RuntimeError(
            "wrapt is required for parlot-instrumentation-livekit. "
            "Install with: pip install wrapt"
        )
    if isinstance(entrypoint_fnc, wrapt.FunctionWrapper):
        return entrypoint_fnc
    return _parlot_entrypoint_wrapper(entrypoint_fnc)


def _patch_job_proc_entrypoint() -> None:
    """Wrap the job entrypoint inside the job subprocess, not on WorkerOptions.

    LiveKit ``dev`` mode pickles ``AgentServer`` (including ``entrypoint_fnc``) into a
    spawned worker via ``watchfiles``. Wrapping at ``WorkerOptions`` time produces a
    non-picklable wrapper (nested function or ``__main__`` name collision).

    We instead patch ``_JobProc.__init__`` so the wrapt wrapper is created only after
    the user's function has been unpickled in the job process.
    """
    try:
        from livekit.agents.ipc.job_proc_lazy_main import _JobProc
    except ImportError:
        logger.debug("livekit-agents not importable; skipping _JobProc patch")
        return

    if getattr(_JobProc, "_parlot_patched", False):
        return

    _original_init = _JobProc.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        if self._job_entrypoint_fnc is not None:
            self._job_entrypoint_fnc = _wrap_entrypoint(self._job_entrypoint_fnc)

    _JobProc.__init__ = _patched_init
    _JobProc._parlot_patched = True
    logger.debug("Patched _JobProc.__init__ for auto job context registration")


def _patch_job_context_connect() -> None:
    """Re-register room context after ``JobContext.connect`` (room SID is available then)."""
    try:
        from livekit.agents import JobContext
    except ImportError:
        logger.debug("livekit-agents not importable; skipping JobContext.connect patch")
        return

    if getattr(JobContext, "_parlot_connect_patched", False):
        return

    _original_connect = JobContext.connect

    async def _patched_connect(self, *args, **kwargs):
        result = await _original_connect(self, *args, **kwargs)
        try:
            from ._platform_refs import register_livekit_job_context_from_ctx

            await register_livekit_job_context_from_ctx(self)
        except Exception:
            logger.debug(
                "Could not refresh job context after connect", exc_info=True
            )
        return result

    JobContext.connect = _patched_connect
    JobContext._parlot_connect_patched = True
    logger.debug("Patched JobContext.connect for room SID refresh")


def _patch_agent_session_with_tracer(provider) -> None:
    """Patch AgentSession using the tracer from our provider."""
    import opentelemetry.trace as trace

    tracer = provider.get_tracer("parlot.instrumentation.livekit")

    from ._hooks import _patch_agent_session
    _patch_agent_session(tracer)
