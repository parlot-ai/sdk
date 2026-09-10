"""Capture Python ``logging`` records for active Parlot sessions.

Hard requirements:
- Never raises into the customer agent
- Drop records without an active ``session.id``
- Bounded buffer + background flush + circuit breaker
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
import weakref
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from parlot.core.logs_capture import (
    DEFAULT_LOGS_MIN_LEVEL,
    ParlotizeCaptureLogs,
    level_at_least,
    normalize_log_level,
    should_capture_logs,
)
from parlot.core.session import get_active_session

if TYPE_CHECKING:
    from parlot.core.context import ParlotContext

# Bounded ring buffer — drop oldest under pressure.
_MAX_BUFFER = 256
_CIRCUIT_FAILURES = 3
_CIRCUIT_COOLDOWN_S = 60.0
_FLUSH_INTERVAL_S = 5.0
_MAX_MESSAGE_LEN = 4096
_MAX_BATCH = 100

_SKIP_LOGGER_PREFIXES = (
    "opentelemetry",
    "parlot.core.logging",
    "parlot.core.session_logs",
    "httpx",
    "httpcore",
    "urllib3",
)

SessionResolver = Callable[[], Optional[dict[str, Any]]]


@dataclass
class SessionLogRecord:
    session_id: str
    conversation_id: str
    ts: str
    level: str
    logger_name: str
    message: str
    turn_index: int = 0
    trace_id: str = ""
    span_id: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


def _current_trace_span() -> tuple[str, str]:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is None or not getattr(ctx, "is_valid", False):
            return "", ""
        return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    except Exception:
        return "", ""


def _resolve_session_fields(
    session_resolver: Optional[SessionResolver],
) -> Optional[dict[str, Any]]:
    if session_resolver is not None:
        try:
            resolved = session_resolver()
            if resolved and resolved.get("session_id"):
                return resolved
        except Exception:
            pass
    state = get_active_session()
    if state is not None and state.session_id:
        # Prefer LiveKit-style parlot_session_id when present.
        sid = str(
            getattr(state, "parlot_session_id", "") or state.session_id
        )
        if not sid:
            return None
        conversation_id = str(getattr(state, "conversation_id", "") or sid)
        turn_index = int(getattr(state, "turn_count", 0) or 0)
        open_agent = getattr(state, "open_agent_turn_index", None)
        if open_agent is not None:
            try:
                turn_index = int(open_agent)
            except (TypeError, ValueError):
                pass
        return {
            "session_id": sid,
            "conversation_id": conversation_id,
            "turn_index": turn_index,
        }
    return None


def _severity_number(level: str):
    from opentelemetry._logs import SeverityNumber

    key = (level or "INFO").upper()
    mapping = {
        "TRACE": SeverityNumber.TRACE,
        "DEBUG": SeverityNumber.DEBUG,
        "INFO": SeverityNumber.INFO,
        "WARN": SeverityNumber.WARN,
        "WARNING": SeverityNumber.WARN,
        "ERROR": SeverityNumber.ERROR,
        "FATAL": SeverityNumber.FATAL,
        "CRITICAL": SeverityNumber.FATAL,
    }
    return mapping.get(key, SeverityNumber.INFO)


def _encode_otlp_logs(events: list[SessionLogRecord]) -> bytes:
    """Encode session log events as OTLP ``ExportLogsServiceRequest`` protobuf."""
    from opentelemetry.context import Context
    from opentelemetry.exporter.otlp.proto.common._log_encoder import encode_logs
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import (
        LogRecordExporter,
        LogRecordExportResult,
        SimpleLogRecordProcessor,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import (
        NonRecordingSpan,
        SpanContext,
        TraceFlags,
        set_span_in_context,
    )

    class _Capture(LogRecordExporter):
        def __init__(self) -> None:
            self.batch: list[Any] = []

        def export(self, batch: Any) -> LogRecordExportResult:  # type: ignore[override]
            self.batch.extend(list(batch))
            return LogRecordExportResult.SUCCESS

        def shutdown(self) -> None:
            return None

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True

    by_scope: dict[str, list[SessionLogRecord]] = {}
    for event in events:
        scope = (event.logger_name or "parlot.session").strip() or "parlot.session"
        by_scope.setdefault(scope, []).append(event)

    captured: list[Any] = []
    for scope_name, scope_events in by_scope.items():
        provider = LoggerProvider(resource=Resource.create({}))
        capture = _Capture()
        provider.add_log_record_processor(SimpleLogRecordProcessor(capture))
        logger = provider.get_logger(scope_name)
        for event in scope_events:
            ctx: Context | None = None
            if event.trace_id and event.span_id:
                try:
                    tid = int(event.trace_id, 16)
                    sid = int(event.span_id, 16)
                    span_ctx = SpanContext(
                        trace_id=tid,
                        span_id=sid,
                        is_remote=False,
                        trace_flags=TraceFlags(0x01),
                    )
                    ctx = set_span_in_context(NonRecordingSpan(span_ctx))
                except ValueError:
                    ctx = None
            attrs: dict[str, Any] = {
                "session.id": event.session_id,
                "session.conversation_id": event.conversation_id or event.session_id,
                "turn.index": int(event.turn_index or 0),
            }
            for k, v in (event.attributes or {}).items():
                if k and v is not None:
                    attrs[str(k)[:128]] = str(v)[:1024]
            ts_ns: int | None = None
            try:
                dt = datetime.strptime(event.ts[:23], "%Y-%m-%d %H:%M:%S.%f")
                ts_ns = int(
                    dt.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000
                )
            except Exception:
                ts_ns = None
            logger.emit(
                timestamp=ts_ns,
                context=ctx,
                severity_number=_severity_number(event.level),
                severity_text=(event.level or "INFO").upper(),
                body=event.message[:_MAX_MESSAGE_LEN],
                attributes=attrs,
            )
        captured.extend(capture.batch)
        try:
            provider.shutdown()
        except Exception:
            pass

    if not captured:
        return b""
    request = encode_logs(captured)
    return request.SerializeToString()


class SessionLogHandler(logging.Handler):
    """Root logging handler that buffers session-correlated log lines."""

    def __init__(self, collector: SessionLogsCollector) -> None:
        super().__init__()
        self._collector = collector

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._collector.handle_record(self, record)
        except Exception:
            return


class SessionLogsCollector:
    """Per-``ParlotContext`` session log capture pipeline."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffer: deque[SessionLogRecord] = deque(maxlen=_MAX_BUFFER)
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._last_flush_at = 0.0
        self._endpoint = ""
        self._api_key = ""
        self._flush_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._handler: Optional[SessionLogHandler] = None
        self._installed = False
        self._atexit_registered = False
        self._parlotize_capture_logs: ParlotizeCaptureLogs = None
        self._parlotize_log_level: Optional[str] = None
        self._session_resolver: Optional[SessionResolver] = None
        self._agent_id_resolver: Optional[Callable[[], str]] = None
        self._metadata_resolver: Optional[Callable[[], Optional[bool]]] = None
        self._context_ref: Optional[weakref.ref[ParlotContext]] = None

    def bind_context(self, context: ParlotContext) -> None:
        self._context_ref = weakref.ref(context)

    def _runtime(self):
        ctx = self._context_ref() if self._context_ref is not None else None
        return ctx.runtime if ctx is not None else None

    def set_capture_logs_parlotize(
        self,
        capture_logs: ParlotizeCaptureLogs = None,
        *,
        log_level: Optional[str] = None,
    ) -> None:
        self._parlotize_capture_logs = capture_logs
        if log_level is not None:
            self._parlotize_log_level = normalize_log_level(log_level)

    def set_resolvers(
        self,
        *,
        session_resolver: Optional[SessionResolver] = None,
        agent_id_resolver: Optional[Callable[[], str]] = None,
        metadata_resolver: Optional[Callable[[], Optional[bool]]] = None,
    ) -> None:
        """Optional framework hooks (e.g. LiveKit job bootstrap fallback)."""
        if session_resolver is not None:
            self._session_resolver = session_resolver
        if agent_id_resolver is not None:
            self._agent_id_resolver = agent_id_resolver
        if metadata_resolver is not None:
            self._metadata_resolver = metadata_resolver

    def _resolve_min_level(self) -> str:
        if self._parlotize_log_level:
            return self._parlotize_log_level
        runtime = self._runtime()
        if runtime is not None:
            agent_id = ""
            if self._agent_id_resolver is not None:
                try:
                    agent_id = self._agent_id_resolver() or ""
                except Exception:
                    agent_id = ""
            if agent_id:
                agent_levels = runtime.logs_agent_min_levels_map()
                if agent_id in agent_levels:
                    return normalize_log_level(agent_levels[agent_id])
            if runtime.logs_min_level:
                return normalize_log_level(runtime.logs_min_level)
        return DEFAULT_LOGS_MIN_LEVEL

    def capture_logs_enabled_for_agent(self, agent_name: str = "") -> bool:
        runtime = self._runtime()
        metadata = None
        if self._metadata_resolver is not None:
            try:
                metadata = self._metadata_resolver()
            except Exception:
                metadata = None
        name = agent_name
        if not name and self._agent_id_resolver is not None:
            try:
                name = self._agent_id_resolver() or ""
            except Exception:
                name = ""
        return should_capture_logs(
            name,
            metadata_capture_logs=metadata,
            parlotize_capture_logs=self._parlotize_capture_logs,
            bootstrap_globs=list(runtime.logs_globs) if runtime else None,
            bootstrap_agents=runtime.logs_agents_map() if runtime else None,
            bootstrap_present=runtime is not None and runtime.logs_policy_present,
        )

    def handle_record(
        self, handler: logging.Handler, record: logging.LogRecord
    ) -> None:
        name = record.name or ""
        if any(name == p or name.startswith(p + ".") for p in _SKIP_LOGGER_PREFIXES):
            return
        level_name = record.levelname or "INFO"
        if not level_at_least(level_name, self._resolve_min_level()):
            return
        if not self.capture_logs_enabled_for_agent():
            return
        session = _resolve_session_fields(self._session_resolver)
        if not session or not session.get("session_id"):
            return
        message = handler.format(record) if handler.formatter else record.getMessage()
        if not isinstance(message, str):
            message = str(message)
        trace_id, span_id = _current_trace_span()
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]
        attrs: dict[str, str] = {}
        if record.pathname:
            attrs["pathname"] = str(record.pathname)[:512]
        if record.lineno:
            attrs["lineno"] = str(record.lineno)
        if record.funcName:
            attrs["funcName"] = str(record.funcName)[:128]
        event = SessionLogRecord(
            session_id=str(session["session_id"]),
            conversation_id=str(session.get("conversation_id") or session["session_id"]),
            ts=ts,
            level=normalize_log_level(level_name),
            logger_name=name,
            message=message,
            turn_index=int(session.get("turn_index") or 0),
            trace_id=trace_id,
            span_id=span_id,
            attributes=attrs,
        )
        with self._lock:
            self._buffer.append(event)

    def init(self, *, endpoint: str = "", api_key: str = "") -> None:
        """Install root handler + start background flusher."""
        with self._lock:
            self._endpoint = (endpoint or "").rstrip("/")
            self._api_key = api_key or ""
            if self._handler is None:
                self._handler = SessionLogHandler(self)
                self._handler.setLevel(logging.DEBUG)
                self._handler.setFormatter(logging.Formatter("%(message)s"))
            if not self._installed:
                logging.root.addHandler(self._handler)
                self._installed = True
            if self._flush_thread is None or not self._flush_thread.is_alive():
                self._stop.clear()
                self._flush_thread = threading.Thread(
                    target=self._flush_loop,
                    name="parlot-session-logs-flush",
                    daemon=True,
                )
                self._flush_thread.start()
            if not self._atexit_registered:
                atexit.register(self.shutdown)
                self._atexit_registered = True

    def drain(self) -> list[SessionLogRecord]:
        with self._lock:
            events = list(self._buffer)
            self._buffer.clear()
            return events

    def snapshot(self) -> list[SessionLogRecord]:
        with self._lock:
            return list(self._buffer)

    def _circuit_open(self) -> bool:
        return time.time() < self._circuit_open_until

    def _flush_loop(self) -> None:
        while not self._stop.wait(_FLUSH_INTERVAL_S):
            try:
                self._try_flush()
            except Exception:
                continue

    def _try_flush(self, *, force: bool = False) -> None:
        if self._circuit_open():
            with self._lock:
                self._buffer.clear()
            return
        if not self._endpoint or not self._api_key:
            return

        if not force:
            now = time.time()
            if now - self._last_flush_at < _FLUSH_INTERVAL_S * 0.5:
                return

        events = self.drain()
        if not events:
            return

        ok = self._post_events(events)
        self._last_flush_at = time.time()
        if ok:
            self._consecutive_failures = 0
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= _CIRCUIT_FAILURES:
            self._circuit_open_until = time.time() + _CIRCUIT_COOLDOWN_S
            self._consecutive_failures = 0

    def _post_events(self, events: list[SessionLogRecord]) -> bool:
        try:
            import httpx
        except Exception:
            return False

        url = f"{self._endpoint}/v1/logs"
        try:
            payload = _encode_otlp_logs(events[:_MAX_BATCH])
        except Exception:
            return False
        if not payload:
            return True
        from parlot.core.provider import build_parlot_client_headers

        headers = build_parlot_client_headers(self._api_key)
        headers["Content-Type"] = "application/x-protobuf"
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.post(
                    url,
                    content=payload,
                    headers=headers,
                )
                return 200 <= res.status_code < 300
        except Exception:
            return False

    def shutdown(self) -> None:
        """Stop capture and push any remaining buffered logs. Never raises."""
        try:
            self._stop.set()
            thread = self._flush_thread
            if (
                thread is not None
                and thread.is_alive()
                and thread is not threading.current_thread()
            ):
                thread.join(timeout=1.0)
            self._flush_thread = None
            with self._lock:
                if self._installed and self._handler is not None:
                    try:
                        logging.root.removeHandler(self._handler)
                    except Exception:
                        pass
                    self._installed = False
            self._try_flush(force=True)
        except Exception:
            return
