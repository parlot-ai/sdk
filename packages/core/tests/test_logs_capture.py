"""Session log capture policy: default on when bootstrap missing."""

from __future__ import annotations

from parlot.core.logs_capture import should_capture_logs


class TestShouldCaptureLogs:
    def test_defaults_on_without_bootstrap(self) -> None:
        assert should_capture_logs("receptionist") is True
        assert should_capture_logs("") is True

    def test_bootstrap_absent_still_on(self) -> None:
        assert should_capture_logs("x", bootstrap_present=False) is True

    def test_bootstrap_star_allowlist(self) -> None:
        assert (
            should_capture_logs(
                "anything",
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is True
        )

    def test_empty_globs_off(self) -> None:
        assert (
            should_capture_logs(
                "receptionist",
                bootstrap_globs=[],
                bootstrap_present=True,
            )
            is False
        )

    def test_bootstrap_pattern_allowlist(self) -> None:
        assert (
            should_capture_logs(
                "receptionist-main",
                bootstrap_globs=["receptionist*", "cal-*"],
                bootstrap_present=True,
            )
            is True
        )
        assert (
            should_capture_logs(
                "other",
                bootstrap_globs=["receptionist*", "cal-*"],
                bootstrap_present=True,
            )
            is False
        )

    def test_metadata_true_override(self) -> None:
        assert (
            should_capture_logs(
                "receptionist",
                metadata_capture_logs=True,
                bootstrap_globs=[],
                bootstrap_present=True,
            )
            is True
        )

    def test_metadata_false_override(self) -> None:
        assert (
            should_capture_logs(
                "receptionist",
                metadata_capture_logs=False,
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is False
        )

    def test_parlotize_bool_false_beats_bootstrap(self) -> None:
        assert (
            should_capture_logs(
                "foo",
                parlotize_capture_logs=False,
                bootstrap_globs=["*"],
                bootstrap_present=True,
            )
            is False
        )

    def test_parlotize_allowlist(self) -> None:
        assert (
            should_capture_logs("foo", parlotize_capture_logs=["foo"]) is True
        )
        assert (
            should_capture_logs("bar", parlotize_capture_logs=["foo"]) is False
        )

    def test_bootstrap_agent_toggle_false_beats_globs(self) -> None:
        assert (
            should_capture_logs(
                "receptionist",
                bootstrap_globs=["*"],
                bootstrap_agents={"receptionist": False},
                bootstrap_present=True,
            )
            is False
        )

    def test_parlotize_beats_bootstrap(self) -> None:
        assert (
            should_capture_logs(
                "receptionist",
                parlotize_capture_logs=True,
                bootstrap_agents={"receptionist": False},
                bootstrap_present=True,
            )
            is True
        )

    def test_metadata_beats_parlotize(self) -> None:
        assert (
            should_capture_logs(
                "receptionist",
                metadata_capture_logs=False,
                parlotize_capture_logs=True,
            )
            is False
        )
