"""Lightweight language detection for turn metadata (en/es heuristic)."""

from __future__ import annotations

import re

_EN_MARKERS = re.compile(
    r"\b("
    r"the|and|you|that|was|for|are|with|this|have|from|hello|thanks|please|"
    r"want|need|can|would|could|about|your|what|how|when|where|why|who"
    r")\b",
    re.IGNORECASE,
)
_ES_MARKERS = re.compile(
    r"\b("
    r"el|la|los|las|que|de|en|un|una|por|con|para|está|hola|gracias|quiero|"
    r"necesito|puedo|sobre|tu|su|qué|cómo|cuándo|dónde|porqué|quién|llamo|"
    r"tarde|hablar|habla"
    r")\b",
    re.IGNORECASE,
)


def detect_language_from_text(text: str) -> str | None:
    trimmed = text.strip()
    if len(trimmed) < 6:
        return None

    en_hits = len(_EN_MARKERS.findall(trimmed))
    es_hits = len(_ES_MARKERS.findall(trimmed))
    if en_hits == 0 and es_hits == 0:
        return None
    if en_hits > es_hits:
        return "en"
    if es_hits > en_hits:
        return "es"
    return None
