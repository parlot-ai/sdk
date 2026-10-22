"""Pipecat-specific platform.ref.* registry and span stamping."""

from __future__ import annotations

import logging

from parlot.core.platform_refs import stamp_platform_refs as _stamp_platform_refs

from .attrs import PIPECAT_FRAMEWORK

logger = logging.getLogger("parlot.instrumentation.pipecat")


def _pipecat_platform_ref_triples(
    *,
    conversation_id: str = "",
    transport: str = "",
    transport_room: str = "",
) -> list[tuple[str, str, str]]:
    refs: list[tuple[str, str, str]] = []
    if conversation_id:
        refs.append((PIPECAT_FRAMEWORK, "conversation_id", conversation_id))
    if transport_room:
        kind = f"{transport}_room" if transport else "room"
        refs.append((PIPECAT_FRAMEWORK, kind, transport_room))
    return refs


def stamp_pipecat_platform_refs(
    span,
    *,
    conversation_id: str = "",
    transport: str = "",
    transport_room: str = "",
) -> None:
    """Stamp ``platform.ref.*`` triples for Pipecat session resolve."""
    refs = _pipecat_platform_ref_triples(
        conversation_id=conversation_id,
        transport=transport,
        transport_room=transport_room,
    )
    if refs:
        _stamp_platform_refs(span, refs)
