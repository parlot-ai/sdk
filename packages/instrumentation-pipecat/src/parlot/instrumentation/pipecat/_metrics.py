"""Pipecat process-scoped wiring for core :class:`ParlotMetricsRecorder`."""

from __future__ import annotations

import logging

from opentelemetry.sdk.resources import Resource

from parlot.core.metrics import (
    LONG_LIVED_METRICS_EXPORT_INTERVAL_MS,
    ParlotMetricsRecorder,
    build_parlot_meter_provider,
)

from .attrs import PIPECAT_FRAMEWORK

logger = logging.getLogger("parlot.instrumentation.pipecat")

_recorder: ParlotMetricsRecorder | None = None
_meter_endpoint: str = ""
_meter_api_key: str = ""
_meter_resource: Resource | None = None


def configure_metrics_endpoint(
    endpoint: str, api_key: str, resource: Resource
) -> None:
    global _meter_endpoint, _meter_api_key, _meter_resource
    _meter_endpoint = endpoint
    _meter_api_key = api_key
    _meter_resource = resource


def build_meter_provider(endpoint: str, api_key: str, resource: Resource):
    return build_parlot_meter_provider(
        endpoint,
        resource,
        api_key=api_key,
        export_interval_millis=LONG_LIVED_METRICS_EXPORT_INTERVAL_MS,
        quiet=True,
    )


def set_metrics_recorder(recorder: ParlotMetricsRecorder | None) -> None:
    global _recorder
    _recorder = recorder


def get_metrics_recorder() -> ParlotMetricsRecorder | None:
    """Return the active recorder, recreating after a post-session shutdown."""
    global _recorder
    if _recorder is not None:
        return _recorder
    if not _meter_endpoint or _meter_resource is None:
        return None
    try:
        provider = build_meter_provider(
            _meter_endpoint, _meter_api_key, _meter_resource
        )
        _recorder = ParlotMetricsRecorder(
            provider,
            meter_name="parlot.instrumentation.pipecat",
            framework=PIPECAT_FRAMEWORK,
        )
    except Exception:
        logger.debug("Could not recreate Pipecat metrics recorder", exc_info=True)
        return None
    return _recorder


def shutdown_metrics() -> None:
    """Flush and stop periodic export (call on session close)."""
    global _recorder
    rec = _recorder
    _recorder = None
    if rec is None:
        return
    try:
        rec.shutdown(10_000)
    except Exception:
        logger.debug("metrics shutdown failed", exc_info=True)
