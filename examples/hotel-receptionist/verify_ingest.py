"""Verify a Parlot session closed and landed in Postgres + Tinybird Local.

Usage:
  uv run python verify_ingest.py <parlot_session_id>
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _pg_scalar(sql: str) -> str:
    import subprocess

    out = subprocess.check_output(
        ["psql", os.environ["DATABASE_URL"], "-Atc", sql],
        text=True,
    ).strip()
    return out


def _tb_sql(sql: str) -> dict:
    host = os.environ.get("TINYBIRD_BASE_URL", "http://127.0.0.1:7181").rstrip("/")
    token = os.environ["TINYBIRD_TOKEN"]
    url = f"{host}/v0/sql?{urllib.parse.urlencode({'q': sql})}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def verify(session_id: str, *, wait_s: float = 90.0) -> int:
    deadline = time.time() + wait_s
    last_status = ""
    while time.time() < deadline:
        last_status = _pg_scalar(
            "SELECT coalesce(status,'missing') FROM session_close_runs "
            f"WHERE session_id='{session_id}' ORDER BY attempt_n DESC LIMIT 1"
        )
        if last_status == "completed":
            break
        time.sleep(1.5)
    else:
        print(f"FAIL: session_close_runs status={last_status or 'missing'} (timeout)")
        return 1

    open_flag = _pg_scalar(
        f"SELECT session_open::text FROM session_hot_meta WHERE session_id='{session_id}'"
    )
    turns = _pg_scalar(
        f"SELECT count(*)::text FROM session_turns WHERE session_id='{session_id}'"
    )
    print(f"pg session_open={open_flag} close_status={last_status} turns={turns}")
    if open_flag != "false":
        print("FAIL: session_hot_meta.session_open is not false")
        return 1
    if int(turns or "0") < 1:
        print("FAIL: no session_turns")
        return 1

    tb = _tb_sql(
        "SELECT session_id, agent_id, end_state, end_reason "
        f"FROM sessions WHERE session_id='{session_id}' "
        "ORDER BY attempt_n DESC LIMIT 1 FORMAT JSON"
    )
    rows = tb.get("data") or []
    if not rows:
        print("FAIL: no Tinybird sessions row")
        return 1
    row = rows[0]
    print(
        f"tb agent_id={row.get('agent_id')} end_state={row.get('end_state')} "
        f"end_reason={row.get('end_reason')}"
    )
    # end_state is product outcome (completed/error/…); any sessions row means close flushed.
    if not row.get("end_state"):
        print("FAIL: Tinybird sessions row missing end_state")
        return 1

    spans = _tb_sql(
        f"SELECT count() AS n FROM session_spans WHERE session_id='{session_id}' FORMAT JSON"
    )
    recordings = _tb_sql(
        f"SELECT count() AS n FROM session_recordings WHERE session_id='{session_id}' FORMAT JSON"
    )
    span_n = (spans.get("data") or [{"n": 0}])[0]["n"]
    rec_n = (recordings.get("data") or [{"n": 0}])[0]["n"]
    print(f"tb session_spans={span_n} session_recordings={rec_n}")
    if span_n < 1:
        print("FAIL: no session_spans")
        return 1
    if rec_n != 0:
        print("FAIL: unexpected session_recordings with record=False")
        return 1

    print("OK")
    return 0


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    here = Path(__file__).resolve().parent
    for candidate in (
        Path(os.environ["PLATFORM_ENV_FILE"]) if os.environ.get("PLATFORM_ENV_FILE") else None,
        here.parents[2] / "platform" / ".env.local",  # …/parlot.ai/platform
        Path.home() / "dev/parlot.ai/platform/.env.local",
    ):
        if candidate is not None:
            _load_dotenv(candidate)
    _load_dotenv(here / ".env")
    for key in ("DATABASE_URL", "TINYBIRD_TOKEN"):
        if not os.environ.get(key):
            print(f"missing {key} (load platform .env.local)", file=sys.stderr)
            raise SystemExit(2)
    raise SystemExit(verify(sys.argv[1]))


if __name__ == "__main__":
    main()
