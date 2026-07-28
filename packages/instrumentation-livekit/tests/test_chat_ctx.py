"""Tests for LiveKit chat context instruction extraction."""

from __future__ import annotations

import json

from parlot.instrumentation.livekit._chat_ctx import (
    full_instructions_excerpt,
    instructions_excerpt_from_chat_ctx,
    static_instructions_excerpt,
    static_instructions_excerpt_from_chat_ctx,
)


def _chat_ctx(*items: dict) -> str:
    return json.dumps({"items": list(items)})


STATIC_GREETER_CONFIG = (
    "You are a friendly restaurant receptionist.\n"
    "Your jobs are to greet the caller."
)
RUNTIME_GREETER = (
    "You are Greeter agent. Current user data is checked_out: false\n"
    "customer_name: carlos"
)


def test_instructions_excerpt_collapses_repeated_system_blocks() -> None:
    block = "You are a friendly greeter.\n\nAnswer warmly."
    raw = _chat_ctx(
        {"type": "message", "role": "system", "content": [block]},
        {"type": "message", "role": "system", "content": [block]},
        {"type": "message", "role": "system", "content": [block]},
    )
    excerpt = instructions_excerpt_from_chat_ctx(raw)
    assert excerpt.count("You are a friendly greeter.") == 1


def test_instructions_excerpt_preserves_unique_block_order() -> None:
    first = "Block A"
    second = "Block B"
    raw = _chat_ctx(
        {"type": "agent_config_update", "instructions": first},
        {"type": "message", "role": "system", "content": [second]},
        {"type": "agent_config_update", "instructions": first},
        {"type": "message", "role": "system", "content": [second]},
    )
    excerpt = instructions_excerpt_from_chat_ctx(raw)
    assert excerpt == f"{first}\n\n{second}"


def test_instructions_excerpt_normalizes_whitespace_before_dedupe() -> None:
    block = "Same text"
    raw = _chat_ctx(
        {"type": "message", "role": "system", "content": [f"  {block}  \n\n"]},
        {"type": "message", "role": "system", "content": [block]},
    )
    excerpt = instructions_excerpt_from_chat_ctx(raw)
    assert excerpt == block


def test_full_excerpt_keeps_runtime_system_messages() -> None:
    raw = _chat_ctx(
        {"type": "agent_config_update", "instructions": STATIC_GREETER_CONFIG},
        {"type": "message", "role": "system", "content": [RUNTIME_GREETER]},
    )
    excerpt = instructions_excerpt_from_chat_ctx(raw)
    assert STATIC_GREETER_CONFIG in excerpt
    assert "Current user data" in excerpt


def test_static_excerpt_uses_config_update_only() -> None:
    raw = _chat_ctx(
        {"type": "agent_config_update", "instructions": STATIC_GREETER_CONFIG},
        {"type": "message", "role": "system", "content": [RUNTIME_GREETER]},
    )
    excerpt = static_instructions_excerpt_from_chat_ctx(raw)
    assert STATIC_GREETER_CONFIG in excerpt
    assert "Current user data" not in excerpt


def test_static_excerpt_includes_lk_instructions() -> None:
    raw = _chat_ctx(
        {"type": "agent_config_update", "instructions": STATIC_GREETER_CONFIG},
        {"type": "message", "role": "system", "content": [RUNTIME_GREETER]},
    )
    excerpt = static_instructions_excerpt(raw, "Bootstrap prompt")
    assert "Bootstrap prompt" in excerpt
    assert STATIC_GREETER_CONFIG in excerpt
    assert "Current user data" not in excerpt


def test_full_excerpt_includes_lk_instructions_and_runtime_messages() -> None:
    raw = _chat_ctx(
        {"type": "agent_config_update", "instructions": STATIC_GREETER_CONFIG},
        {"type": "message", "role": "system", "content": [RUNTIME_GREETER]},
    )
    excerpt = full_instructions_excerpt(raw, "Bootstrap prompt")
    assert "Bootstrap prompt" in excerpt
    assert STATIC_GREETER_CONFIG in excerpt
    assert "Current user data" in excerpt
