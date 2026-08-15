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


def resolve_capture_content(capture_content: Optional[bool] = None) -> Optional[bool]:
    """Return the explicit ``configure(capture_content=)`` override, or None.

    When None, callers should resolve via ``should_capture_content`` against
    bootstrap policy (default on).
    """
    if capture_content is not None:
        return bool(capture_content)
    return None


def build_resource(
    *,
    service_name: Optional[str] = None,
    service_version: Optional[str] = None,
) -> Resource:
    attrs = {service_attributes.SERVICE_NAME: service_name or "unknown"}
    if service_version:
        attrs[service_attributes.SERVICE_VERSION] = service_version
    return Resource.create(attrs)


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
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
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
