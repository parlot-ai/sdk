"""
Parlot platform.ref.* helpers for session resolve / debug linking.

Framework-agnostic span stamping only. Framework-specific registries and
triple construction live in each instrumentation package (e.g. LiveKit).
"""

from __future__ import annotations

from .attrs import (
    ATTR_PLATFORM_FRAMEWORK,
    ATTR_PLATFORM_KIND,
    ATTR_PLATFORM_REF_PREFIX,
    ATTR_PLATFORM_VALUE,
)


def platform_ref_flat_key(kind: str) -> str:
    """Flat ``platform.ref.{kind}`` attribute key for ingestion fallbacks."""
    return f"{ATTR_PLATFORM_REF_PREFIX}{kind}"


def stamp_platform_refs(
    span,
    refs: list[tuple[str, str, str]],
) -> None:
    """Stamp ``platform.ref.*`` triples onto a span.

    ``refs`` is a list of ``(framework, kind, value)`` tuples, e.g.
    ``("livekit", "room_sid", "RM_abc")``. The first tuple is also written
    to the canonical triple attributes (``platform.ref.framework/kind/value``)
    so backends can pivot on a single primary ref.

    Every tuple is also written as a flat ``platform.ref.{kind} = value`` key
    for ingestion fallbacks.

    Args:
        span: A ``ReadableSpan`` (or any object with a mutable ``_attributes``
            dict), as produced by ``ParlotBaseProcessor``.
        refs: Non-empty list of reference triples.
    """
    if not refs:
        return
    if span._attributes is None:
        span._attributes = {}

    fw, kind, val = refs[0]
    span._attributes[ATTR_PLATFORM_FRAMEWORK] = fw
    span._attributes[ATTR_PLATFORM_KIND] = kind
    span._attributes[ATTR_PLATFORM_VALUE] = val

    for fw_i, kind_i, val_i in refs:
        span._attributes[platform_ref_flat_key(kind_i)] = val_i
