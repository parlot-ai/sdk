"""Tests for table-driven GenAI span rename helpers."""

from __future__ import annotations

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from parlot.core.attrs import (
    ATTR_AGENT_STAGE,
    ATTR_GEN_AI_MODEL,
    ATTR_GEN_AI_OP_NAME,
    GEN_AI_OP_CHAT,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
    span_name_chat,
)
from parlot.core.span_rename import apply_genai_span_rename, remap_native_span_name


def test_remap_native_span_name_families() -> None:
    assert (
        remap_native_span_name(
            "llm",
            {ATTR_GEN_AI_MODEL: "gpt"},
            llm_names=("llm",),
            unknown="drop",
        )
        == span_name_chat("gpt")
    )
    assert (
        remap_native_span_name("tts", tts_names=("tts",), unknown="drop")
        == SPAN_VOICE_TTS
    )
    assert (
        remap_native_span_name("stt", stt_names=("stt",), unknown="drop")
        == SPAN_VOICE_STT
    )
    assert (
        remap_native_span_name("turn", drop_names=("turn",), unknown="drop") is None
    )
    assert (
        remap_native_span_name("vendor", unknown="passthrough") == "vendor"
    )
    assert remap_native_span_name("vendor", unknown="drop") is None


def test_apply_genai_span_rename_mutates_name_and_op() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    span = tracer.start_span("llm", attributes={ATTR_GEN_AI_MODEL: "m"})
    span.end()
    finished: ReadableSpan = exporter.get_finished_spans()[0]

    apply_genai_span_rename(
        finished,
        remap_fn=lambda n, a: remap_native_span_name(
            n, a, llm_names=("llm",), unknown="drop"
        ),
        stage_for_native={"llm": "request"},
        llm_names=("llm",),
    )
    assert finished.name == span_name_chat("m")
    assert finished.attributes[ATTR_AGENT_STAGE] == "request"
    assert finished.attributes[ATTR_GEN_AI_OP_NAME] == GEN_AI_OP_CHAT
