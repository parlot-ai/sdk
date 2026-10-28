"""Shared TracerProvider / OTLP bootstrap for instrumentation packages."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, Sequence

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.semconv.attributes import service_attributes

logger = logging.getLogger("parlot.core.provider")


def resolve_endpoint(endpoint: Optional[str] = None) -> str:
    """Resolve OTLP base endpoint from kwarg or ``PARLOT_ENDPOINT``."""
    return (endpoint or os.environ.get("PARLOT_ENDPOINT", "") or "").rstrip("/")


def resolve_api_key(api_key: Optional[str] = None) -> str:
    """Resolve API key from kwarg or ``PARLOT_API_KEY``."""
    return api_key or os.environ.get("PARLOT_API_KEY", "") or ""


def resolve_capture_genai_content(capture_genai_content: Optional[bool] = None) -> Optional[bool]:
    """Return the explicit ``parlotize(capture_genai_content=)`` override, or None.

    When None, callers should resolve via ``should_capture_genai_content`` against
    bootstrap policy (default on).
    """
    if capture_genai_content is not None:
        return bool(capture_genai_content)
    return None


def resolve_service_name(
    service_name: Optional[str] = None,
    *,
    agent_id: str = "",
) -> str:
    """Resolve OTel ``service.name``: explicit kwarg, else ``agent_id``, else ``unknown``.

    Matches ``ParlotizeProtocol`` / adapter docs so every instrumentation uses the
    same default without repeating framework fallbacks.
    """
    name = (service_name or "").strip() or (agent_id or "").strip()
    return name or "unknown"


def build_resource(
    *,
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
    agent_id: str = "",
) -> Resource:
    attrs = {
        service_attributes.SERVICE_NAME: resolve_service_name(
            service_name,
            agent_id=agent_id,
        ),
    }
    if service_version:
        attrs[service_attributes.SERVICE_VERSION] = service_version
    return Resource.create(attrs)


INGESTION_PROTOCOL_VERSION = "1"
HEADER_SDK_NAME = "x-parlot-sdk-name"
HEADER_SDK_VERSION = "x-parlot-sdk-version"
HEADER_INGESTION_VERSION = "x-parlot-ingestion-version"


def build_parlot_client_headers(api_key: str = "") -> dict[str, str]:
    """Build standard transport headers sent with Parlot telemetry exports."""
    from parlot.core.sdk_version import resolve_parlot_sdk_version

    version = resolve_parlot_sdk_version() or "unknown"
    headers: dict[str, str] = {
        HEADER_SDK_NAME: "parlot-python",
        HEADER_SDK_VERSION: version,
        HEADER_INGESTION_VERSION: INGESTION_PROTOCOL_VERSION,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def build_otlp_http_exporter(
    *,
    endpoint: str,
    api_key: str = "",
) -> SpanExporter:
    """Build an OTLP/HTTP span exporter targeting ``{endpoint}/v1/traces``."""
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    if not endpoint:
        raise ValueError(
            "No OTLP endpoint configured. Pass endpoint= or set the "
            "PARLOT_ENDPOINT environment variable."
        )
    headers = build_parlot_client_headers(api_key)
    trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
    return OTLPSpanExporter(endpoint=trace_endpoint, headers=headers)


def build_tracer_provider(
    *,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
    span_processors: Sequence[SpanProcessor] = (),
    span_exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Build a ``TracerProvider`` with optional processors and OTLP export.

    When ``span_exporter`` is omitted, builds a default OTLP/HTTP exporter to
    ``{endpoint}/v1/traces``. Callers typically wrap that exporter (filter,
    sanitize, quiet) before passing it here.
    """
    resolved_endpoint = resolve_endpoint(endpoint)
    resolved_api_key = resolve_api_key(api_key)
    resource = build_resource(
        service_name=service_name,
        service_version=service_version,
    )
    exporter = span_exporter
    if exporter is None:
        exporter = build_otlp_http_exporter(
            endpoint=resolved_endpoint,
            api_key=resolved_api_key,
        )

    provider = TracerProvider(resource=resource)
    for processor in span_processors:
        provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def adopt_existing_tracer_provider() -> Any | None:
    """Return the global tracer provider when already set by another Parlot package.

    Returns ``None`` when only the default no-op / proxy provider is installed.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider

    provider = trace.get_tracer_provider()
    if isinstance(provider, SdkTracerProvider):
        return provider
    return None


def try_set_global_tracer_provider(provider: Any) -> bool:
    """Set the global tracer provider, swallowing failures (already set, etc.)."""
    from opentelemetry import trace

    try:
        trace.set_tracer_provider(provider)
        return True
    except Exception:
        logger.debug("Could not set global tracer provider", exc_info=True)
        return False


def attach_span_processor_if_absent(
    provider: Any,
    factory: Any,
    *,
    processor_type: type | None = None,
) -> bool:
    """Attach a span processor when the SDK provider does not already have one.

    ``factory`` is a zero-arg callable that returns a ``SpanProcessor``.
    ``processor_type`` defaults to the type of the first factory result check —
    when omitted, skips the duplicate check and always adds.

    Returns True when a processor was attached.
    """
    from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider

    if not isinstance(provider, SdkTracerProvider):
        return False

    if processor_type is not None:
        try:
            active = getattr(provider, "_active_span_processor", None)
            procs = getattr(active, "_span_processors", None) or getattr(
                active, "_processors", None
            )
            if procs and any(isinstance(p, processor_type) for p in procs):
                return False
        except Exception:
            pass
    try:
        provider.add_span_processor(factory())
        return True
    except Exception:
        logger.debug("Could not attach span processor", exc_info=True)
        return False


def build_filtered_tracer_provider(
    *,
    endpoint: str,
    api_key: str,
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
    span_processors: Sequence[SpanProcessor] = (),
) -> TracerProvider:
    """Build a TracerProvider with ``ExportFilterSpanExporter`` over OTLP/HTTP.

    Framework processors go in ``span_processors`` (before the batch exporter).
    """
    from parlot.core.export import ExportFilterSpanExporter

    resource = build_resource(
        service_name=service_name,
        service_version=service_version,
    )
    otlp = build_otlp_http_exporter(endpoint=endpoint, api_key=api_key)
    exporter = ExportFilterSpanExporter(otlp)
    provider = TracerProvider(resource=resource)
    for processor in span_processors:
        provider.add_span_processor(processor)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider
