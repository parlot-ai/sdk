"""Room composite egress starts without LiveKit webhook config."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from parlot.core.context import ParlotContext
from parlot.core.runtime import ParlotRuntimeContext
from parlot.instrumentation.livekit import _auto
from parlot.instrumentation.livekit._egress import maybe_start_room_composite_egress


@pytest.fixture(autouse=True)
def _reset_runtime():
    _auto.set_configured_context(None)
    _auto._configured_record = True
    yield
    _auto.set_configured_context(None)
    _auto._configured_record = None


def _platform(**kwargs) -> ParlotRuntimeContext:
    defaults = dict(
        endpoint="https://ingest.test",
        api_key="key",
        tenant_id="org-1",
        content_bucket="bucket",
        r2_endpoint="https://r2.example.com",
    )
    defaults.update(kwargs)
    return ParlotRuntimeContext(**defaults)


@pytest.mark.asyncio
async def test_egress_starts_without_webhooks(monkeypatch) -> None:
    context = ParlotContext()
    context.runtime = _platform()
    _auto.set_configured_context(context)

    bootstrap = MagicMock()
    bootstrap.session_id = "sess-1"
    bootstrap.session_span = None
    bootstrap.processor = MagicMock()
    bootstrap.processor._context = context

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

    api_mod = SimpleNamespace(
        EncodedFileType=SimpleNamespace(OGG="ogg"),
        EncodedFileOutput=MagicMock(return_value=encoded_file_output),
        S3Upload=MagicMock(return_value=s3_upload),
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
    lkapi.egress.start_room_composite_egress.assert_awaited_once_with(room_composite_req)
    bootstrap.processor.set_recording_anchor_wall_ms.assert_called_once()


@pytest.mark.asyncio
async def test_egress_failure_logs_descriptively_without_traceback(
    monkeypatch, caplog
) -> None:
    context = ParlotContext()
    context.runtime = _platform()
    _auto.set_configured_context(context)

    bootstrap = MagicMock()
    bootstrap.session_id = "sess-1"
    bootstrap.session_span = MagicMock()
    bootstrap.session_span.is_recording.return_value = True
    bootstrap.processor = MagicMock()
    bootstrap.processor._context = context

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

    class FakeServerError(Exception):
        def __init__(self, code: str, message: str):
            super().__init__(f"ServerError(code={code}, message={message})")
            self.code = code
            self.message = message

    api_mod = SimpleNamespace(
        EncodedFileType=SimpleNamespace(OGG="ogg"),
        EncodedFileOutput=MagicMock(),
        S3Upload=MagicMock(),
        RoomCompositeEgressRequest=MagicMock(),
        LiveKitAPI=MagicMock(),
    )
    lkapi = api_mod.LiveKitAPI.return_value
    lkapi.egress.start_room_composite_egress = AsyncMock(
        side_effect=FakeServerError("not_found", "requested room does not exist")
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
        with caplog.at_level("DEBUG"):
            await maybe_start_room_composite_egress(ctx)

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    assert "StartRoomCompositeEgress failed — not_found: requested room does not exist" in error_records[0].message
    assert error_records[0].exc_info is None

