"""Room composite egress starts without LiveKit webhook signing key."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parlot.core.runtime import (
    ParlotRuntimeContext,
    clear_runtime,
    set_runtime,
)
from parlot.instrumentation.livekit import _auto
from parlot.instrumentation.livekit._egress import maybe_start_room_composite_egress
from parlot.instrumentation.livekit._runtime_context import (
    LiveKitRuntimeContext,
    clear_livekit_runtime,
    set_livekit_runtime,
)


@pytest.fixture(autouse=True)
def _reset_runtime():
    clear_runtime()
    clear_livekit_runtime()
    _auto._configured_record = True
    yield
    clear_runtime()
    clear_livekit_runtime()
    _auto._configured_record = None


def _platform(**kwargs) -> ParlotRuntimeContext:
    defaults = dict(
        endpoint="https://ingest.test",
        api_key="key",
        org_id="org-1",
        content_bucket="bucket",
        r2_endpoint="https://r2.example.com",
        egress_webhook_url="https://ingest.test/v1/integrations/livekit/webhook",
    )
    defaults.update(kwargs)
    return ParlotRuntimeContext(**defaults)


@pytest.mark.asyncio
async def test_egress_starts_without_webhook_signing_key(monkeypatch) -> None:
    platform = _platform()
    set_runtime(platform)
    set_livekit_runtime(LiveKitRuntimeContext(platform=platform, webhook_signing_key=""))

    bootstrap = MagicMock()
    bootstrap.session_id = "sess-1"
    bootstrap.session_span = None
    bootstrap.processor = MagicMock()

    grant = {
        "filepath": "org-1/sessions/sess-1/audio.ogg",
        "audio_recording_uri": "r2://bucket/org-1/sessions/sess-1/audio.ogg",
        "s3": {
            "access_key": "ak",
            "secret": "sk",
            "bucket": "bucket",
            "endpoint": "https://r2.example.com",
            "force_path_style": True,
        },
    }

    encoded_file_output = MagicMock(name="EncodedFileOutput")
    room_composite_req = MagicMock(name="RoomCompositeEgressRequest")
    s3_upload = MagicMock(name="S3Upload")
    webhook_config = MagicMock(name="WebhookConfig")

    api_mod = SimpleNamespace(
        EncodedFileType=SimpleNamespace(OGG="ogg"),
        EncodedFileOutput=MagicMock(return_value=encoded_file_output),
        S3Upload=MagicMock(return_value=s3_upload),
        WebhookConfig=MagicMock(return_value=webhook_config),
        RoomCompositeEgressRequest=MagicMock(return_value=room_composite_req),
        LiveKitAPI=MagicMock(),
    )
    lkapi = api_mod.LiveKitAPI.return_value
    lkapi.egress.start_room_composite_egress = AsyncMock(
        return_value=SimpleNamespace(egress_id="EG_1")
    )
    lkapi.aclose = AsyncMock()

    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example")
    monkeypatch.setenv("LIVEKIT_API_KEY", "APIxxx")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")

    ctx = MagicMock()
    ctx.room = SimpleNamespace(name="room-1")
    ctx.job = SimpleNamespace(metadata='{"record": true}', agent_name="agent", dispatch_id=None)

    with (
        patch(
            "parlot.instrumentation.livekit._session.get_job_bootstrap",
            return_value=bootstrap,
        ),
        patch(
            "parlot.instrumentation.livekit._egress._fetch_upload_grant",
            new_callable=AsyncMock,
            return_value=grant,
        ),
        patch.dict("sys.modules", {"livekit": SimpleNamespace(api=api_mod), "livekit.api": api_mod}),
    ):
        await maybe_start_room_composite_egress(ctx)

    api_mod.RoomCompositeEgressRequest.assert_called_once()
    kwargs = api_mod.RoomCompositeEgressRequest.call_args.kwargs
    assert kwargs["room_name"] == "room-1"
    assert kwargs["audio_only"] is True
    assert "webhooks" not in kwargs
    api_mod.WebhookConfig.assert_not_called()
    lkapi.egress.start_room_composite_egress.assert_awaited_once_with(room_composite_req)
    bootstrap.processor.set_recording_anchor_wall_ms.assert_called_once()


@pytest.mark.asyncio
async def test_egress_includes_webhook_when_signing_key_present(monkeypatch) -> None:
    platform = _platform()
    set_runtime(platform)
    set_livekit_runtime(
        LiveKitRuntimeContext(platform=platform, webhook_signing_key="APIkey")
    )

    bootstrap = MagicMock()
    bootstrap.session_id = "sess-2"
    bootstrap.session_span = None
    bootstrap.processor = MagicMock()

    grant = {
        "filepath": "org-1/sessions/sess-2/audio.ogg",
        "audio_recording_uri": "r2://bucket/org-1/sessions/sess-2/audio.ogg",
        "s3": {
            "access_key": "ak",
            "secret": "sk",
            "bucket": "bucket",
            "endpoint": "https://r2.example.com",
            "force_path_style": True,
        },
    }

    encoded_file_output = MagicMock(name="EncodedFileOutput")
    room_composite_req = MagicMock(name="RoomCompositeEgressRequest")
    webhook_config = MagicMock(name="WebhookConfig")

    api_mod = SimpleNamespace(
        EncodedFileType=SimpleNamespace(OGG="ogg"),
        EncodedFileOutput=MagicMock(return_value=encoded_file_output),
        S3Upload=MagicMock(),
        WebhookConfig=MagicMock(return_value=webhook_config),
        RoomCompositeEgressRequest=MagicMock(return_value=room_composite_req),
        LiveKitAPI=MagicMock(),
    )
    lkapi = api_mod.LiveKitAPI.return_value
    lkapi.egress.start_room_composite_egress = AsyncMock(
        return_value=SimpleNamespace(egress_id="EG_2")
    )
    lkapi.aclose = AsyncMock()

    monkeypatch.setenv("LIVEKIT_URL", "wss://lk.example")
    monkeypatch.setenv("LIVEKIT_API_KEY", "APIxxx")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")

    ctx = MagicMock()
    ctx.room = SimpleNamespace(name="room-2")
    ctx.job = SimpleNamespace(metadata='{"record": true}', agent_name="agent", dispatch_id=None)

    with (
        patch(
            "parlot.instrumentation.livekit._session.get_job_bootstrap",
            return_value=bootstrap,
        ),
        patch(
            "parlot.instrumentation.livekit._egress._fetch_upload_grant",
            new_callable=AsyncMock,
            return_value=grant,
        ),
        patch.dict("sys.modules", {"livekit": SimpleNamespace(api=api_mod), "livekit.api": api_mod}),
    ):
        await maybe_start_room_composite_egress(ctx)

    api_mod.WebhookConfig.assert_called_once_with(
        url=platform.egress_webhook_url,
        signing_key="APIkey",
    )
    kwargs = api_mod.RoomCompositeEgressRequest.call_args.kwargs
    assert kwargs["webhooks"] == [webhook_config]
