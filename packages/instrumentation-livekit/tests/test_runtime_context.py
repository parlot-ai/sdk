"""Bootstrap runtime caching (platform vs LiveKit recording)."""

from __future__ import annotations

from parlot.instrumentation.livekit._runtime_context import (
    apply_bootstrap_payload,
    clear_livekit_runtime,
    get_livekit_runtime,
)
from parlot.core.runtime import clear_runtime, get_runtime


class TestApplyBootstrapPayload:
    def setup_method(self) -> None:
        clear_runtime()
        clear_livekit_runtime()

    def teardown_method(self) -> None:
        clear_runtime()
        clear_livekit_runtime()

    def test_platform_only_when_signing_key_missing(self) -> None:
        payload = {
            "org_id": "org-1",
            "content_bucket": "bucket",
            "r2_endpoint": "https://r2.example.com",
            "egress_webhook_url": "https://ingest.test/webhook",
        }
        assert apply_bootstrap_payload("https://ingest.test", "key", payload) is False
        runtime = get_runtime()
        assert runtime is not None
        assert runtime.org_id == "org-1"
        assert get_livekit_runtime() is None

    def test_livekit_runtime_when_signing_key_present(self) -> None:
        payload = {
            "org_id": "org-1",
            "content_bucket": "bucket",
            "r2_endpoint": "https://r2.example.com",
            "egress_webhook_url": "https://ingest.test/webhook",
            "livekit_webhook_signing_key": "APIkey",
        }
        assert apply_bootstrap_payload("https://ingest.test", "key", payload) is True
        lk = get_livekit_runtime()
        assert lk is not None
        assert lk.webhook_signing_key == "APIkey"
        runtime = get_runtime()
        assert runtime is not None
        assert runtime.org_id == lk.platform.org_id
        assert runtime.egress_webhook_url == lk.platform.egress_webhook_url
