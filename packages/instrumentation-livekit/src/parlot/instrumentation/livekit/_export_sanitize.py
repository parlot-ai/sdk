"""Strip LiveKit vendor attribute keys from OTLP-bound spans."""

from __future__ import annotations

from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.util.types import Attributes


def _is_vendor_attribute_key(key: str) -> bool:
    return key.startswith("lk.") or key.startswith("lk.agents.")


def _sanitized_attributes(attrs: Attributes | None) -> Attributes | None:
    if not attrs:
        return attrs
    filtered = {k: v for k, v in attrs.items() if not _is_vendor_attribute_key(str(k))}
    return filtered or None


class _SanitizedReadableSpan:
    """ReadableSpan view with vendor-prefixed attributes removed."""

    def __init__(self, inner: ReadableSpan) -> None:
        self._inner = inner
        self._attributes = _sanitized_attributes(inner.attributes)

    @property
    def attributes(self) -> Attributes | None:
        return self._attributes

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class SanitizeVendorAttrsSpanExporter(SpanExporter):
    """Remove ``lk.*`` keys so exported OTLP matches the framework-agnostic contract."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if not spans:
            return SpanExportResult.SUCCESS
        cleaned = [_SanitizedReadableSpan(span) for span in spans]
        return self._exporter.export(cleaned)

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)
