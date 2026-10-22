"""Patch Pipecat PipelineWorker so tracing/metrics stay on after parlotize()."""

from __future__ import annotations

import inspect
import logging
from typing import Any

logger = logging.getLogger("parlot.instrumentation.pipecat")

_patched = False


def install_pipeline_worker_hooks() -> None:
    """Ensure PipelineWorker enables tracing, turn tracking, and metrics."""
    global _patched
    if _patched:
        return

    worker_cls = None
    params_cls = None
    try:
        from pipecat.pipeline.worker import PipelineParams, PipelineWorker

        worker_cls = PipelineWorker
        params_cls = PipelineParams
    except ImportError:
        try:
            from pipecat.pipeline.task import PipelineParams, PipelineTask

            worker_cls = PipelineTask
            params_cls = PipelineParams
        except ImportError:
            logger.warning(
                "parlot: pipecat PipelineWorker not importable; "
                "enable_tracing=True must be set manually"
            )
            return

    original_init = worker_cls.__init__
    init_params = inspect.signature(original_init).parameters
    supports_turn_tracking = "enable_turn_tracking" in init_params

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        params = kwargs.get("params")
        if params is None and len(args) >= 2 and isinstance(args[1], params_cls):
            params = args[1]
        if params is None:
            kwargs["params"] = params_cls(
                enable_metrics=True,
                enable_usage_metrics=True,
            )
        else:
            for flag in ("enable_metrics", "enable_usage_metrics"):
                if hasattr(params, flag) and not getattr(params, flag):
                    try:
                        setattr(params, flag, True)
                    except Exception:
                        pass

        kwargs.setdefault("enable_tracing", True)
        if supports_turn_tracking:
            kwargs.setdefault("enable_turn_tracking", True)

        original_init(self, *args, **kwargs)

    worker_cls.__init__ = patched_init  # type: ignore[method-assign]
    _patched = True
    logger.debug("parlot: patched Pipecat %s for tracing defaults", worker_cls.__name__)
