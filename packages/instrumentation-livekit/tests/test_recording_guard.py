"""LiveKit job context adapters for recording policy."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from parlot.core.runtime import ParlotRuntimeContext, clear_runtime, set_runtime
from parlot.instrumentation.livekit import _auto
from parlot.instrumentation.livekit._recording_guard import (
    agent_name_from_ctx,
    recording_agent_id_from_ctx,
    should_capture_genai_content,
    should_record,
)


def _ctx(metadata=None, agent_name="receptionist", dispatch_id=None):
    job = MagicMock()
    job.agent_name = agent_name
    job.dispatch_id = dispatch_id
    job.metadata = metadata
    job.metadata_json = None
    return MagicMock(job=job)


@pytest.fixture(autouse=True)
def _reset_recording_state():
    clear_runtime()
    _auto._configured_record = None
    _auto._configured_capture_genai_content = None
    _auto._configured_agent_id = None
    yield
    clear_runtime()
    _auto._configured_record = None
    _auto._configured_capture_genai_content = None
    _auto._configured_agent_id = None


class TestLiveKitRecordingGuard:
    def test_defaults_off(self) -> None:
        assert should_record(_ctx()) is False

    def test_metadata_true_override(self) -> None:
        meta = json.dumps({"record": True})
        assert should_record(_ctx(metadata=meta)) is True

    def test_metadata_false_override(self) -> None:
        set_runtime(
            ParlotRuntimeContext(
                endpoint="http://localhost",
                api_key="k",
                org_id="o",
                content_bucket="b",
                r2_endpoint="http://r2",
                recording_globs=("*",),
            )
        )
        meta = json.dumps({"record": False})
        assert should_record(_ctx(metadata=meta)) is False

    def test_bootstrap_star_records_unnamed_worker(self) -> None:
        set_runtime(
            ParlotRuntimeContext(
                endpoint="http://localhost",
                api_key="k",
                org_id="o",
                content_bucket="b",
                r2_endpoint="http://r2",
                recording_globs=("*",),
            )
        )
        assert should_record(_ctx(agent_name="", dispatch_id="AD_GAJ5UrwGKqsZ")) is True

    def test_configure_record_true(self) -> None:
        _auto._configured_record = True
        assert should_record(_ctx()) is True

    def test_configure_agent_id_uses_bootstrap_agents_map(self) -> None:
        _auto._configured_agent_id = "custom-id"
        set_runtime(
            ParlotRuntimeContext(
                endpoint="http://localhost",
                api_key="k",
                org_id="o",
                content_bucket="b",
                r2_endpoint="http://r2",
                recording_agents=(("custom-id", True),),
            )
        )
        assert should_record(_ctx(agent_name="other")) is True
        assert recording_agent_id_from_ctx(_ctx(agent_name="other")) == "custom-id"

    def test_agent_name_from_ctx_ignores_dispatch_id(self) -> None:
        assert (
            agent_name_from_ctx(_ctx(agent_name="", dispatch_id="AD_NrRASAvBPGAx"))
            == ""
        )

    def test_agent_name_from_ctx_returns_explicit_name(self) -> None:
        assert (
            agent_name_from_ctx(
                _ctx(agent_name="hotel-receptionist", dispatch_id="AD_xxx")
            )
            == "hotel-receptionist"
        )

    def test_agent_name_from_ctx_rejects_dispatch_shaped_agent_name(self) -> None:
        assert agent_name_from_ctx(_ctx(agent_name="AD_fSkdjADywDrh")) == ""


class TestLiveKitGenAIContentCaptureGuard:
    def test_defaults_on(self) -> None:
        assert should_capture_genai_content(_ctx()) is True

    def test_bootstrap_agent_override(self) -> None:
        set_runtime(
            ParlotRuntimeContext(
                endpoint="http://localhost",
                api_key="k",
                org_id="o",
                content_bucket="b",
                r2_endpoint="http://r2",
                capture_genai_content_globs=("*",),
                capture_genai_content_agents=(("receptionist", False),),
                capture_genai_content_policy_present=True,
            )
        )
        assert should_capture_genai_content(_ctx(agent_name="receptionist")) is False
        assert should_capture_genai_content(_ctx(agent_name="other")) is True

    def test_empty_globs_off(self) -> None:
        set_runtime(
            ParlotRuntimeContext(
                endpoint="http://localhost",
                api_key="k",
                org_id="o",
                content_bucket="b",
                r2_endpoint="http://r2",
                capture_genai_content_globs=(),
                capture_genai_content_policy_present=True,
            )
        )
        assert should_capture_genai_content(_ctx()) is False

    def test_metadata_and_configure_overrides(self) -> None:
        set_runtime(
            ParlotRuntimeContext(
                endpoint="http://localhost",
                api_key="k",
                org_id="o",
                content_bucket="b",
                r2_endpoint="http://r2",
                capture_genai_content_globs=(),
                capture_genai_content_policy_present=True,
            )
        )
        assert should_capture_genai_content(_ctx(metadata=json.dumps({"capture_genai_content": True}))) is True
        _auto._configured_capture_genai_content = False
        assert should_capture_genai_content(_ctx()) is False
