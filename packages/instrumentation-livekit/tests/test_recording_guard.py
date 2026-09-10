"""LiveKit job context adapters for recording policy."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from parlot.core.context import ParlotContext
from parlot.core.runtime import ParlotRuntimeContext
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


def _parlot_ctx(**runtime_kwargs) -> ParlotContext:
    context = ParlotContext()
    if runtime_kwargs:
        context.runtime = ParlotRuntimeContext(
            endpoint="http://localhost",
            api_key="k",
            tenant_id="o",
            content_bucket="b",
            r2_endpoint="http://r2",
            **runtime_kwargs,
        )
    return context


@pytest.fixture(autouse=True)
def _reset_recording_state():
    _auto.set_configured_context(None)
    _auto._configured_record = None
    _auto._configured_capture_genai_content = None
    _auto._configured_agent_id = None
    yield
    _auto.set_configured_context(None)
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
        context = _parlot_ctx(recording_globs=("*",))
        _auto.set_configured_context(context)
        meta = json.dumps({"record": False})
        assert should_record(_ctx(metadata=meta), context=context) is False

    def test_bootstrap_star_records_unnamed_worker(self) -> None:
        context = _parlot_ctx(recording_globs=("*",))
        _auto.set_configured_context(context)
        assert (
            should_record(
                _ctx(agent_name="", dispatch_id="AD_GAJ5UrwGKqsZ"), context=context
            )
            is True
        )

    def test_parlotize_record_true(self) -> None:
        _auto._configured_record = True
        assert should_record(_ctx()) is True

    def test_parlotize_agent_id_uses_bootstrap_agents_map(self) -> None:
        _auto._configured_agent_id = "custom-id"
        context = _parlot_ctx(recording_agents=(("custom-id", True),))
        _auto.set_configured_context(context)
        assert should_record(_ctx(agent_name="other"), context=context) is True
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
        context = _parlot_ctx(
            capture_genai_content_globs=("*",),
            capture_genai_content_agents=(("receptionist", False),),
            capture_genai_content_policy_present=True,
        )
        _auto.set_configured_context(context)
        assert (
            should_capture_genai_content(
                _ctx(agent_name="receptionist"), context=context
            )
            is False
        )
        assert (
            should_capture_genai_content(_ctx(agent_name="other"), context=context)
            is True
        )

    def test_empty_globs_off(self) -> None:
        context = _parlot_ctx(
            capture_genai_content_globs=(),
            capture_genai_content_policy_present=True,
        )
        _auto.set_configured_context(context)
        assert should_capture_genai_content(_ctx(), context=context) is False

    def test_metadata_and_parlotize_overrides(self) -> None:
        context = _parlot_ctx(
            capture_genai_content_globs=(),
            capture_genai_content_policy_present=True,
        )
        _auto.set_configured_context(context)
        assert (
            should_capture_genai_content(
                _ctx(metadata=json.dumps({"capture_genai_content": True})),
                context=context,
            )
            is True
        )
        _auto._configured_capture_genai_content = False
        assert should_capture_genai_content(_ctx(), context=context) is False
