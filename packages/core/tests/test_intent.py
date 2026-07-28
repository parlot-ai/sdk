"""Tests for intent derivation."""

from parlot.core.intent import derive_intent


def test_derive_intent_uses_first_line_as_label() -> None:
    out = derive_intent(
        "greeter",
        "You are a friendly restaurant receptionist.\nRoute callers.",
    )
    assert out["intent_key"] == "greeter"
    assert out["intent_label"] == "You are a friendly restaurant receptionist."
    assert "restaurant" in out["instructions_excerpt"]


def test_derive_intent_title_from_id_when_no_instructions() -> None:
    out = derive_intent("takeaway", "")
    assert out["intent_label"] == "Takeaway"
    assert out["instructions_excerpt"] == ""
