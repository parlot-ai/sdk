"""Bootstrap runtime parsing for logs agent overrides."""

from __future__ import annotations

from parlot.core.runtime import clear_runtime, runtime_from_bootstrap, set_runtime
from parlot.core.session import SessionState, clear_active_session, set_active_session
from parlot.core.session_logs import (
    SessionLogHandler,
    drain_session_logs,
    set_capture_logs_configure,
    set_session_log_resolvers,
    shutdown_session_logs,
)
import logging


def test_runtime_parses_logs_agent_objects() -> None:
    ctx = runtime_from_bootstrap(
        "https://ingest.test",
        "key",
        {
            "org_id": "org-1",
            "content_bucket": "b",
            "r2_endpoint": "https://r2",
            "egress_webhook_url": "https://wh",
            "logs": {
                "globs": ["*"],
                "min_level": "INFO",
                "agents": {
                    "on-org-level": {"enabled": True},
                    "on-debug": {"enabled": True, "min_level": "DEBUG"},
                    "off": {"enabled": False},
                    "ignored-bool": True,
                    "ignored-missing-enabled": {"min_level": "ERROR"},
                },
            },
        },
    )
    assert ctx.logs_agents_map() == {
        "on-org-level": True,
        "on-debug": True,
        "off": False,
    }
    assert ctx.logs_agent_min_levels_map() == {"on-debug": "DEBUG"}
    assert ctx.logs_min_level == "INFO"
    assert ctx.logs_policy_present is True


def test_handler_uses_agent_min_level_from_bootstrap() -> None:
    clear_runtime()
    set_capture_logs_configure(None)
    # Clear configure log_level (API only sets when provided).
    sl_mod = __import__("parlot.core.session_logs", fromlist=["session_logs"])
    sl_mod._configure_log_level = None
    set_session_log_resolvers(agent_id_resolver=lambda: "on-debug")
    set_runtime(
        runtime_from_bootstrap(
            "https://ingest.test",
            "key",
            {
                "org_id": "org-1",
                "content_bucket": "b",
                "r2_endpoint": "https://r2",
                "egress_webhook_url": "https://wh",
                "logs": {
                    "globs": ["*"],
                    "min_level": "WARNING",
                    "agents": {
                        "on-debug": {"enabled": True, "min_level": "DEBUG"},
                    },
                },
            },
        )
    )
    try:
        set_active_session(None, SessionState(session_id="sess"))
        handler = SessionLogHandler()
        info = logging.LogRecord(
            name="my.agent",
            level=logging.INFO,
            pathname="a.py",
            lineno=1,
            msg="info",
            args=(),
            exc_info=None,
        )
        handler.emit(info)
        events = drain_session_logs()
        assert len(events) == 1
        assert events[0].message == "info"
    finally:
        drain_session_logs()
        clear_active_session()
        set_session_log_resolvers(agent_id_resolver=lambda: "")
        sl_mod._configure_log_level = None
        set_capture_logs_configure(None)
        clear_runtime()
        shutdown_session_logs()
