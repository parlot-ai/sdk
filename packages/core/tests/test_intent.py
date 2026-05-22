"""Unit tests for heuristic intent derivation."""

from parlot.core.intent import derive_intent


def test_id_only_when_no_instructions() -> None:
    key, label, excerpt = derive_intent("cancel_task", "")
    assert key == "cancel_task"
    assert label == "Cancel Task"
    assert excerpt == ""


def test_first_line_label_with_instructions() -> None:
    key, label, excerpt = derive_intent(
        "book_appointment",
        "Book appointments for callers.\nMore detail here.",
    )
    assert key == "book_appointment"
    assert label == "Book appointments for callers."
    assert "More detail" in excerpt
