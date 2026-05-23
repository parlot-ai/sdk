"""LiveKit job context adapters for recording policy."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from parlot.instrumentation.livekit._recording_guard import should_record


def _ctx(metadata=None, agent_name="receptionist"):
    job = MagicMock()
    job.agent_name = agent_name
    job.metadata = metadata
    job.metadata_json = None
    return MagicMock(job=job)


class TestLiveKitRecordingGuard:
    def test_unset_env_defaults_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PARLOT_RECORD_AGENTS", raising=False)
        assert should_record(_ctx()) is False

    def test_metadata_true_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PARLOT_RECORD_AGENTS", raising=False)
        meta = json.dumps({"record": True})
        assert should_record(_ctx(metadata=meta)) is True

    def test_metadata_false_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PARLOT_RECORD_AGENTS", "*")
        meta = json.dumps({"record": False})
        assert should_record(_ctx(metadata=meta)) is False
