"""Bootstrap runtime caching for LiveKit instrumentation."""

from __future__ import annotations

from parlot.core.context import ParlotContext
from parlot.instrumentation.livekit._runtime_context import apply_bootstrap_payload


class TestApplyBootstrapPayload:
    def test_caches_platform_runtime(self) -> None:
        context = ParlotContext()
        payload = {
            "org_id": "org-1",
            "content_bucket": "bucket",
            "r2_endpoint": "https://r2.example.com",
            "recording": {
                "globs": ["receptionist*"],
                "agents": {"restaurant-agent": True},
            },
            "capture_genai_content": {
                "globs": ["*"],
                "agents": {"restaurant-agent": False},
            },
        }
        apply_bootstrap_payload(context, "https://ingest.test", "key", payload)
        runtime = context.runtime
        assert runtime is not None
        assert runtime.org_id == "org-1"
        assert runtime.recording_globs == ("receptionist*",)
        assert runtime.recording_agents_map() == {"restaurant-agent": True}
        assert runtime.capture_genai_content_globs == ("*",)
        assert runtime.capture_genai_content_agents_map() == {"restaurant-agent": False}
        assert runtime.capture_genai_content_policy_present is True
