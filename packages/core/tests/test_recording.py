"""Recording policy: metadata > configure > bootstrap."""

from __future__ import annotations

from parlot.core.recording import should_record


class TestShouldRecord:
    def test_defaults_off(self) -> None:
        assert should_record("receptionist") is False

    def test_bootstrap_star_allowlist(self) -> None:
        assert should_record("anything", bootstrap_globs=["*"]) is True

    def test_bootstrap_pattern_allowlist(self) -> None:
        assert (
            should_record(
                "receptionist-main",
                bootstrap_globs=["receptionist*", "cal-*"],
            )
            is True
        )
        assert (
            should_record("other", bootstrap_globs=["receptionist*", "cal-*"])
            is False
        )

    def test_metadata_true_override(self) -> None:
        assert should_record("receptionist", metadata_record=True) is True

    def test_metadata_false_override(self) -> None:
        assert (
            should_record(
                "receptionist",
                metadata_record=False,
                bootstrap_globs=["*"],
            )
            is False
        )

    def test_empty_agent_name_with_star_allowlist(self) -> None:
        assert should_record("", bootstrap_globs=["*"]) is True

    def test_empty_agent_name_without_allowlist(self) -> None:
        assert should_record("") is False

    def test_configure_bool_true(self) -> None:
        assert should_record("foo", configure_record=True) is True

    def test_configure_bool_false_beats_bootstrap(self) -> None:
        assert (
            should_record("foo", configure_record=False, bootstrap_globs=["*"])
            is False
        )

    def test_configure_allowlist(self) -> None:
        assert should_record("foo", configure_record=["foo"]) is True
        assert should_record("bar", configure_record=["foo"]) is False

    def test_bootstrap_agent_toggle_true(self) -> None:
        assert (
            should_record(
                "receptionist",
                bootstrap_agents={"receptionist": True},
            )
            is True
        )

    def test_bootstrap_agent_toggle_false_beats_globs(self) -> None:
        assert (
            should_record(
                "receptionist",
                bootstrap_globs=["*"],
                bootstrap_agents={"receptionist": False},
            )
            is False
        )

    def test_unseen_agent_uses_globs(self) -> None:
        assert (
            should_record(
                "new-agent",
                bootstrap_globs=["new-*"],
                bootstrap_agents={"receptionist": False},
            )
            is True
        )

    def test_configure_beats_bootstrap(self) -> None:
        assert (
            should_record(
                "receptionist",
                configure_record=True,
                bootstrap_agents={"receptionist": False},
            )
            is True
        )
