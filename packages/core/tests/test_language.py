from parlot.core.language import detect_language_from_text


def test_detect_english() -> None:
    assert detect_language_from_text("Hello, I would like to book an appointment") == "en"


def test_detect_spanish() -> None:
    assert (
        detect_language_from_text("Hola, quiero hablar con alguien sobre mi cuenta")
        == "es"
    )


def test_short_text_returns_none() -> None:
    assert detect_language_from_text("hi") is None
