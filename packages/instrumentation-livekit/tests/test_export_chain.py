"""Regression: GenAI rename must run before the export allowlist filter."""

from __future__ import annotations

from unittest.mock import MagicMock

from opentelemetry.sdk.trace.export import SpanExportResult

from parlot.core.attrs import ATTR_AGENT_STAGE, ATTR_GEN_AI_MODEL
from parlot.core.export import ExportFilterSpanExporter
from parlot.instrumentation.livekit._export_filter import EnrichingExportSpanExporter
from parlot.instrumentation.livekit._export_sanitize import SanitizeVendorAttrsSpanExporter
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor


class _RenameSpan:
    """ReadableSpan stand-in that supports ``span._name`` mutation like OTel SDK."""

    def __init__(self, name: str, attrs: dict | None = None) -> None:
        self._name = name
        self._attributes = dict(attrs or {})
        self.context = MagicMock(trace_id=1, span_id=1)
        self.start_time = 1_000_000_000
        self.end_time = 2_000_000_000
        self.status = None
        self.events = ()
        self.links = ()
        self.kind = None
        self.parent = None
        self.resource = None
        self.instrumentation_scope = None
        self.instrumentation_info = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def attributes(self):
        return self._attributes


def _production_like_chain(processor: LiveKitGenAIProcessor, sink: MagicMock):
    """Mirror ``_auto._build_provider`` exporter order after the rename fix."""
    filtered = ExportFilterSpanExporter(sink)
    sanitized = SanitizeVendorAttrsSpanExporter(filtered)
    return EnrichingExportSpanExporter(sanitized, processor)


def test_export_chain_renames_before_filter() -> None:
    processor = LiveKitGenAIProcessor()
    sink = MagicMock()
    sink.export.return_value = SpanExportResult.SUCCESS
    exporter = _production_like_chain(processor, sink)

    batch = [
        _RenameSpan("llm_node", {ATTR_GEN_AI_MODEL: "gpt-4o"}),
        _RenameSpan("tts_node"),
        _RenameSpan("function_tool", {"lk.function_tool.name": "book"}),
        _RenameSpan("user_turn"),
        _RenameSpan("agent_turn"),
        _RenameSpan("eou_detection"),
    ]
    result = exporter.export(batch)
    assert result is SpanExportResult.SUCCESS

    exported = sink.export.call_args[0][0]
    names = sorted(s.name for s in exported)
    assert names == ["chat gpt-4o", "eou_detection", "execute_tool book", "tts"]
    by_name = {s.name: s for s in exported}
    assert by_name["chat gpt-4o"].attributes.get(ATTR_AGENT_STAGE) == "node"
    assert by_name["tts"].attributes.get(ATTR_AGENT_STAGE) == "node"
    # Vendor keys stripped after rename.
    assert "lk.function_tool.name" not in (by_name["execute_tool book"].attributes or {})


def test_legacy_filter_before_enrich_drops_pipeline_ops() -> None:
    """Document the pre-fix breakage: filter before rename drops native ops."""
    processor = LiveKitGenAIProcessor()
    sink = MagicMock()
    sink.export.return_value = SpanExportResult.SUCCESS
    # Outer filter sees native names and drops them before enrich can rename.
    broken = ExportFilterSpanExporter(
        EnrichingExportSpanExporter(sink, processor),
    )
    result = broken.export([_RenameSpan("llm_node"), _RenameSpan("tts_node")])
    assert result is SpanExportResult.SUCCESS
    sink.export.assert_not_called()
