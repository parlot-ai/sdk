"""LLM cost computation. Prices in USD per million tokens (input, output)."""

from __future__ import annotations

from typing import Optional

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o":             (2.50,  10.00),
    "gpt-4o-mini":        (0.15,   0.60),
    "gpt-4.1":            (2.00,   8.00),
    "gpt-4.1-mini":       (0.40,   1.60),
    "gpt-4.1-nano":       (0.10,   0.40),
    "o3":                 (10.00,  40.00),
    "o4-mini":            (1.10,   4.40),
    "claude-opus-4-5":    (15.00,  75.00),
    "claude-sonnet-4-5":  (3.00,   15.00),
    "claude-haiku-4-5":   (0.80,    4.00),
    "gemini-2.5-flash":   (0.15,   0.60),
    "gemini-2.5-pro":     (1.25,   10.00),
}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    prices: dict[str, tuple[float, float]] | None = None,
) -> Optional[float]:
    """Return estimated cost in USD, or None if the model has no price entry."""
    table = prices if prices is not None else DEFAULT_PRICES
    rate = table.get(model)
    if rate is None:
        for key, val in table.items():
            if model.startswith(key):
                rate = val
                break
    if rate is None:
        return None
    return (input_tokens * rate[0] + output_tokens * rate[1]) / 1_000_000
