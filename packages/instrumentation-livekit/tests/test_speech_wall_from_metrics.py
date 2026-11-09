"""User speech_wall synthesis: classic STT vs realtime-degenerate Gemini Live."""

from __future__ import annotations

import time
from unittest.mock import patch

from parlot.instrumentation.livekit._turn_enricher import TurnEnricher


def test_both_timestamps_unchanged() -> None:
    started = 1_700_000_000.0
    stopped = 1_700_000_002.5
    wall = TurnEnricher._speech_wall_ms_from_metrics(
        {"started_speaking_at": started, "stopped_speaking_at": stopped},
        synthesize_missing_end=True,
        last_agent_speech_end_wall_ms=int(started * 1000) - 5_000,
    )
    assert wall == (int(started * 1000), int(stopped * 1000))


def test_classic_missing_stopped_uses_start_to_now() -> None:
    """STT→LLM→TTS: started is true early VAD; end=now yields multi-second window."""
    now = 1_700_000_010.0
    started = now - 3.0  # spoken for ~3s before ChatMessage emit
    with patch(
        "parlot.instrumentation.livekit._turn_enricher.time.time",
        return_value=now,
    ):
        wall = TurnEnricher._speech_wall_ms_from_metrics(
            {"started_speaking_at": started},
            synthesize_missing_end=True,
            last_agent_speech_end_wall_ms=int((now - 10.0) * 1000),
        )
    assert wall is not None
    start_ms, end_ms = wall
    assert start_ms == int(started * 1000)
    assert end_ms == int(now * 1000)
    assert end_ms - start_ms >= TurnEnricher._MIN_SYNTHESIZED_SPEECH_MS


def test_realtime_degenerate_reinterprets_started_as_eou() -> None:
    """Gemini Live: started≈now (EOU), no stopped → [last_agent_end, started]."""
    now = 1_794_259_510.650
    started = now - 0.005  # ~5ms before emit → classic candidate collapses
    agent_end_s = now - 4.0
    agent_end_ms = int(agent_end_s * 1000)
    with patch(
        "parlot.instrumentation.livekit._turn_enricher.time.time",
        return_value=now,
    ):
        wall = TurnEnricher._speech_wall_ms_from_metrics(
            {"started_speaking_at": started},
            synthesize_missing_end=True,
            last_agent_speech_end_wall_ms=agent_end_ms,
        )
    assert wall is not None
    start_ms, end_ms = wall
    assert start_ms == agent_end_ms
    assert end_ms == int(started * 1000)
    assert end_ms - start_ms >= TurnEnricher._MIN_SYNTHESIZED_SPEECH_MS
    # Must not be the ~1–9ms blip at late started.
    assert end_ms - start_ms > 1_000


def test_realtime_degenerate_without_agent_end_returns_none() -> None:
    now = time.time()
    started = now - 0.001
    with patch(
        "parlot.instrumentation.livekit._turn_enricher.time.time",
        return_value=now,
    ):
        wall = TurnEnricher._speech_wall_ms_from_metrics(
            {"started_speaking_at": started},
            synthesize_missing_end=True,
            last_agent_speech_end_wall_ms=0,
        )
    assert wall is None


def test_missing_stopped_without_synthesize_returns_none() -> None:
    wall = TurnEnricher._speech_wall_ms_from_metrics(
        {"started_speaking_at": 1_700_000_000.0},
        synthesize_missing_end=False,
    )
    assert wall is None
