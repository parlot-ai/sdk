"""Runtime topology autodiscovery on session close."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from opentelemetry.sdk.trace import TracerProvider

from parlot.core.attrs import (
    ATTR_AGENT_TRANSFER_FROM,
    ATTR_AGENT_TRANSFER_TO,
    ATTR_SESSION_AGENT_CHAIN,
    ATTR_SESSION_INTENT_SEQUENCE,
    ATTR_SESSION_TOPOLOGY_AGENTS,
    ATTR_SESSION_TOPOLOGY_EDGES,
    ATTR_TOOL_INPUT_PAYLOAD,
    ATTR_TOOL_INPUT_PAYLOAD_PREVIEW,
)
from parlot.instrumentation.livekit.attrs import (
    ATTR_LK_AGENT_LABEL,
    ATTR_LK_CHAT_CTX,
    ATTR_LK_FNC_TOOL_ARGS,
    ATTR_LK_FNC_TOOL_NAME,
    ATTR_LK_FUNCTION_TOOLS,
    ATTR_LK_JOB_ID,
)
from parlot.instrumentation.livekit._processor import LiveKitGenAIProcessor
from parlot.instrumentation.livekit._session import get_job_bootstrap


def _make_span(name: str, attributes: dict | None = None) -> MagicMock:
    span = MagicMock()
    span.name = name
    span._attributes = dict(attributes or {})
    span._events = []
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.context.trace_id = 0xDEADBEEF
    span.attributes = span._attributes
    return span


def test_topology_and_tool_payload_on_session_close() -> None:
    proc = LiveKitGenAIProcessor()
    provider = TracerProvider()
    provider.add_span_processor(proc)
    proc.set_tracer(provider.get_tracer("test"))

    entry = _make_span("job_entrypoint", {ATTR_LK_JOB_ID: "job-topo"})
    proc.on_start(entry)
    bootstrap = get_job_bootstrap()
    session_span = bootstrap.session_span

    chat_ctx = json.dumps(
        [
            {
                "type": "agent_config_update",
                "instructions": "You are the orchestrator for appointments.",
                "tools_added": ["book_appointment"],
            }
        ]
    )

    proc.on_end(
        _make_span(
            "llm_node",
            {
                ATTR_LK_AGENT_LABEL: "orchestrator",
                ATTR_LK_FUNCTION_TOOLS: ("lookup_caller",),
                ATTR_LK_CHAT_CTX: chat_ctx,
            },
        )
    )

    tool_span = _make_span(
        "function_tool",
        {
            ATTR_LK_AGENT_LABEL: "orchestrator",
            ATTR_LK_FNC_TOOL_NAME: "lookup_caller",
            ATTR_LK_FNC_TOOL_ARGS: '{"phone":"+15551212"}',
        },
    )
    proc.on_end(tool_span)
    assert ATTR_TOOL_INPUT_PAYLOAD in tool_span._attributes
    assert ATTR_TOOL_INPUT_PAYLOAD_PREVIEW in tool_span._attributes

    proc.on_end(
        _make_span(
            "lk.agent_handoff",
            {
                ATTR_AGENT_TRANSFER_FROM: "orchestrator",
                ATTR_AGENT_TRANSFER_TO: "cancel_task",
            },
        )
    )

    proc.on_end(entry)

    agents_raw = session_span._attributes.get(ATTR_SESSION_TOPOLOGY_AGENTS)
    assert agents_raw
    agents = json.loads(str(agents_raw))
    assert any(a["id"] == "orchestrator" for a in agents)

    edges_raw = session_span._attributes.get(ATTR_SESSION_TOPOLOGY_EDGES)
    assert edges_raw
    edges = json.loads(str(edges_raw))
    assert any(e["to"] == "lookup_caller" and e["to_kind"] == "tool" for e in edges)
    assert any(e["to"] == "cancel_task" and e["to_kind"] == "agent" for e in edges)

    seq_raw = session_span._attributes.get(ATTR_SESSION_INTENT_SEQUENCE)
    assert seq_raw
    segments = json.loads(str(seq_raw))
    assert any(s["agent_id"] == "cancel_task" for s in segments)
    assert "cancel_task" in str(session_span._attributes.get(ATTR_SESSION_AGENT_CHAIN, ""))
