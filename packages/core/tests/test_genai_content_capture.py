"""Content capture policy: generative AI / tool bodies; default on when bootstrap missing."""

from __future__ import annotations

from parlot.core.genai_content_capture import should_capture_genai_content


class TestShouldCaptureGenAIContent:
    def test_defaults_on_without_bootstrap(self) -> None:
        assert should_capture_genai_content("receptionist") is True
        assert should_capture_genai_content("") is True

    def test_bootstrap_absent_still_on(self) -> None:
        assert should_capture_genai_content("x", bootstrap_present=False) is True

    def test_bootstrap_star_allowlist(self) -> None:
        assert (
            should_capture_genai_content(
                "anything",
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is True
        )

    def test_empty_globs_off(self) -> None:
        assert (
            should_capture_genai_content(
                "receptionist",
                bootstrap_globs=[],
                bootstrap_present=True,
            )
            is False
        )

    def test_bootstrap_pattern_allowlist(self) -> None:
        assert (
            should_capture_genai_content(
                "receptionist-main",
                bootstrap_globs=["receptionist*", "cal-*"],
                bootstrap_present=True,
            )
            is True
        )
        assert (
            should_capture_genai_content(
                "other",
                bootstrap_globs=["receptionist*", "cal-*"],
                bootstrap_present=True,
            )
            is False
        )

    def test_parlotize_bool_false_beats_bootstrap(self) -> None:
        assert (
            should_capture_genai_content(
                "foo",
                capture_genai_content_config=False,
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is False
        )

    def test_parlotize_bool_true_beats_empty_globs(self) -> None:
        assert (
            should_capture_genai_content(
                "foo",
                capture_genai_content_config=True,
                bootstrap_globs=[],
                bootstrap_present=True,
            )
            is True
        )

    def test_metadata_overrides(self) -> None:
        assert (
            should_capture_genai_content(
                "foo",
                metadata_capture_genai_content=False,
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is False
        )
        assert (
            should_capture_genai_content(
                "foo",
                metadata_capture_genai_content=True,
                bootstrap_globs=[],
                bootstrap_present=True,
            )
            is True
        )

    def test_agent_override(self) -> None:
        assert (
            should_capture_genai_content(
                "agent-a",
                bootstrap_agents={"agent-a": False},
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is False
        )
        assert (
            should_capture_genai_content(
                "agent-a",
                bootstrap_agents={"agent-a": True},
                bootstrap_globs=[],
                bootstrap_present=True,
            )
            is True
        )
