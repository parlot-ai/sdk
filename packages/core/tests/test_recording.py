"""PARLOT_RECORD_AGENTS + metadata recording policy."""

from __future__ import annotations

import pytest

from parlot.core.recording import should_record


class TestShouldRecord:
    def test_unset_env_defaults_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PARLOT_RECORD_AGENTS", raising=False)
        assert should_record("receptionist") is False

    def test_star_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PARLOT_RECORD_AGENTS", "*")
        assert should_record("anything") is True

    def test_pattern_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PARLOT_RECORD_AGENTS", "receptionist*,cal-*")
        assert should_record("receptionist-main") is True
        assert should_record("other") is False

    def test_metadata_true_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PARLOT_RECORD_AGENTS", raising=False)
        assert should_record("receptionist", metadata_record=True) is True

    def test_metadata_false_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PARLOT_RECORD_AGENTS", "*")
        assert should_record("receptionist", metadata_record=False) is False

    def test_empty_agent_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PARLOT_RECORD_AGENTS", "*")
        assert should_record("") is False

    def test_explicit_allowlist(self) -> None:
        assert should_record("foo", allowlist=["foo"]) is True
        assert should_record("bar", allowlist=["foo"]) is False
