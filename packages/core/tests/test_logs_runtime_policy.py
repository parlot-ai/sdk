"""Bootstrap runtime parsing for logs agent overrides."""

from __future__ import annotations

import logging

from parlot.core.context import ParlotContext
from parlot.core.runtime import runtime_from_bootstrap
from parlot.core.session import SessionState, clear_active_session, set_active_session
from parlot.core.session_logs import SessionLogHandler


def test_runtime_parses_logs_agent_objects() -> None:
    ctx = runtime_from_bootstrap(
        "https://ingest.test",
        "key",
        {
            "org_id": "org-1",
            "content_bucket": "b",
            "r2_endpoint": "https://r2",
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
    context = ParlotContext()
    context.session_logs.set_capture_logs_configure(None)
    context.session_logs._configure_log_level = None
    context.session_logs.set_resolvers(agent_id_resolver=lambda: "on-debug")
    context.runtime = runtime_from_bootstrap(
        "https://ingest.test",
        "key",
        {
            "org_id": "org-1",
            "content_bucket": "b",
            "r2_endpoint": "https://r2",
            "logs": {
                "globs": ["*"],
                "min_level": "WARNING",
                "agents": {
                    "on-debug": {"enabled": True, "min_level": "DEBUG"},
                },
            },
        },
    )
    try:
        set_active_session(None, SessionState(session_id="sess"))
        handler = SessionLogHandler(context.session_logs)
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
        events = context.session_logs.drain()
        assert len(events) == 1
        assert events[0].message == "info"
    finally:
        context.session_logs.drain()
        clear_active_session()
        context.shutdown()
