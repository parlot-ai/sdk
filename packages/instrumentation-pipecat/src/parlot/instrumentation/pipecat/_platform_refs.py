"""Pipecat-specific platform.ref.* registry and span stamping."""

from __future__ import annotations

import logging

from parlot.core.platform_refs import stamp_framework_refs

from .attrs import PIPECAT_FRAMEWORK

logger = logging.getLogger("parlot.instrumentation.pipecat")


def stamp_pipecat_platform_refs(
    span,
    *,
    conversation_id: str = "",
    transport: str = "",
    transport_room: str = "",
) -> None:
    """Stamp ``platform.ref.*`` triples for Pipecat session resolve."""
    kinds: dict[str, str] = {}
    if conversation_id:
        kinds["conversation_id"] = conversation_id
    if transport_room:
        kind = f"{transport}_room" if transport else "room"
        kinds[kind] = transport_room
    if kinds:
        stamp_framework_refs(span, PIPECAT_FRAMEWORK, **kinds)
