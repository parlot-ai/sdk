"""Drive hotel receptionist sessions with a persona LLM as the guest.

Loads LiveKit-style scenario YAML (PERSONA / OPENING LINE / FACTS / DO), starts
an in-process AgentSession, and alternates agent replies with a second LLM that
role-plays the caller. Each run closes the session so Parlot can finalize
session-close ingest.

Usage:
  uv run python run_persona_sim.py --list
  uv run python run_persona_sim.py --label "Simple room booking by phone"
  uv run python run_persona_sim.py --all --max-turns 24
  uv run python run_persona_sim.py --scenarios scenarios.yaml --tag feature=room_booking --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env.local")
load_dotenv(_ROOT / ".env")

import agent as hotel_agent  # noqa: E402
from common import Userdata  # noqa: E402
from fake_data.seed import build_seed_bytes  # noqa: E402
from hotel_db import TODAY, HotelDB  # noqa: E402
from parlot.instrumentation.livekit import _session as parlot_session  # noqa: E402

from livekit.agents import AgentSession, inference, llm  # noqa: E402

logger = logging.getLogger("hotel-receptionist.persona-sim")

DEFAULT_SCENARIOS = _ROOT / "sim_scenarios.yaml"
DEFAULT_AGENT_MODEL = "google/gemma-4-31b-it"
DEFAULT_PERSONA_MODEL = "openai/gpt-4.1-mini"
_START_SETTLE_S = 0.5
_HANGUP_TOKEN = "HANGUP"

_OPENING_LINE_RE = re.compile(
    r'OPENING LINE:\s*"([^"]+)"',
    re.IGNORECASE | re.MULTILINE,
)

_PERSONA_SYSTEM = """\
You are the PHONE CALLER in a hotel front-desk conversation simulation.
Stay in character for the scenario instructions below.

Rules:
- Speak as the guest/caller only — short, natural phone utterances (usually one sentence).
- Follow PERSONA, OPENING LINE, FACTS, DO (IN ORDER), and REACTIONS exactly.
- Reveal FACTS only when the agent asks; one fact per turn when possible.
- Do not narrate your thoughts, plans, or the fact that you are an AI.
- Do not invent confirmation codes, names, cards, or dates not in FACTS.
- When your DO goals are complete, the agent has finished helping, or you are stuck \
with no useful path forward, reply with exactly {hangup} (nothing else).
""".format(hangup=_HANGUP_TOKEN)


def _load_scenarios(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    scenarios = data.get("scenarios") or []
    if not isinstance(scenarios, list):
        raise SystemExit(f"invalid scenarios file: {path}")
    return scenarios


def _current_parlot_session_id() -> str | None:
    bootstrap = parlot_session._parlot_job_bootstrap.get()
    if bootstrap is None:
        return None
    return bootstrap.session_id


def _format_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if text:
                    parts.append(str(text))
        return " ".join(parts)
    return str(content)


def _assistant_texts(result: Any) -> list[str]:
    texts: list[str] = []
    for event in result.events:
        item = getattr(event, "item", None)
        if item is None:
            continue
        role = getattr(item, "role", None)
        if role == "assistant":
            text = _format_message_text(getattr(item, "content", "")).strip()
            if text:
                texts.append(text)
    return texts


def _print_run_events(result: Any) -> None:
    for event in result.events:
        item = getattr(event, "item", None)
        if item is None:
            continue
        item_type = getattr(item, "type", None) or type(item).__name__
        if item_type == "message" or hasattr(item, "role"):
            role = getattr(item, "role", "?")
            text = _format_message_text(getattr(item, "content", ""))
            print(f"  [{role}] {text}")
        elif hasattr(item, "name") and hasattr(item, "arguments"):
            print(f"  [tool] {item.name}({getattr(item, 'arguments', '')})")
        elif item_type == "function_call_output":
            output = str(getattr(item, "output", ""))
            if len(output) > 160:
                output = output[:157] + "..."
            print(f"  [tool_result] {output}")


def _extract_opening_line(instructions: str) -> str | None:
    match = _OPENING_LINE_RE.search(instructions or "")
    if not match:
        return None
    return match.group(1).strip()


def _tag_match(scenario: dict[str, Any], tag_filter: str) -> bool:
    if "=" not in tag_filter:
        raise SystemExit(f"tag filter must be key=value, got: {tag_filter}")
    key, value = tag_filter.split("=", 1)
    tags = scenario.get("tags") or {}
    if not isinstance(tags, dict):
        return False
    return str(tags.get(key)) == value


async def _persona_reply(
    persona_llm: llm.LLM,
    chat_ctx: llm.ChatContext,
) -> str:
    collected = await persona_llm.chat(chat_ctx=chat_ctx).collect()
    return (collected.text or "").strip()


def _is_hangup(text: str) -> bool:
    cleaned = text.strip().strip('"').strip("'")
    if cleaned.upper() == _HANGUP_TOKEN:
        return True
    # Persona sometimes adds a trailing period or wraps the token.
    return cleaned.upper().rstrip(".!") == _HANGUP_TOKEN


async def _run_scenario(
    scenario: dict[str, Any],
    *,
    agent_model: str,
    persona_model: str,
    max_turns: int,
) -> str:
    label = scenario.get("label") or "(unnamed)"
    instructions = scenario.get("instructions") or ""
    if not instructions.strip():
        raise RuntimeError(f"scenario has no instructions: {label}")

    print(f"\n=== {label} ===")

    db = HotelDB.from_bytes(build_seed_bytes(TODAY))
    session_id: str | None = None
    persona = inference.LLM(persona_model)
    try:
        persona_ctx = llm.ChatContext()
        persona_ctx.add_message(
            role="system",
            content=f"{_PERSONA_SYSTEM}\n\n# Scenario instructions\n{instructions}",
        )

        opening = _extract_opening_line(instructions)
        if not opening:
            seed_ctx = persona_ctx.copy()
            seed_ctx.add_message(
                role="user",
                content=(
                    "The receptionist has just picked up. "
                    "Say your OPENING LINE now (spoken utterance only)."
                ),
            )
            opening = await _persona_reply(persona, seed_ctx)
            if _is_hangup(opening):
                raise RuntimeError("persona hung up before the call started")

        userdata = Userdata(db=db)
        async with AgentSession[Userdata](
            userdata=userdata,
            llm=inference.LLM(agent_model),
            max_tool_steps=5,
        ) as session:
            await session.start(hotel_agent.HotelReceptionistAgent(), capture_run=True)
            await asyncio.sleep(_START_SETTLE_S)
            session_id = _current_parlot_session_id()
            print(f"parlot_session_id={session_id or '(unknown)'}")

            guest_line = opening
            for turn in range(1, max_turns + 1):
                print(f"\n-- turn {turn}/{max_turns} --")
                print(f"  [user] {guest_line}")
                result = await session.run(user_input=guest_line)
                _print_run_events(result)

                # Persona history: assistant = guest, user = agent replies.
                persona_ctx.add_message(role="assistant", content=guest_line)
                agent_texts = _assistant_texts(result)
                agent_blob = "\n".join(agent_texts) if agent_texts else "(no spoken reply)"
                persona_ctx.add_message(
                    role="user",
                    content=f"Receptionist said:\n{agent_blob}\n\nYour next spoken utterance:",
                )

                guest_line = await _persona_reply(persona, persona_ctx)
                if not guest_line:
                    print("  [persona] empty reply — stopping")
                    break
                if _is_hangup(guest_line):
                    print(f"  [persona] {_HANGUP_TOKEN}")
                    break
            else:
                print(f"\n(max turns {max_turns} reached)")

            session_id = _current_parlot_session_id() or session_id

        print(f"\nclosed scenario={label!r} parlot_session_id={session_id or '(unknown)'}")
        if not session_id:
            raise RuntimeError("Parlot session id was not set — configure()/bootstrap may have failed")
        return session_id
    finally:
        try:
            await persona.aclose()
        except Exception:
            logger.exception("error closing persona LLM")
        try:
            await db.aclose()
        except Exception:
            logger.exception("error closing hotel DB for %s", label)


async def _async_main(args: argparse.Namespace) -> int:
    path = Path(args.scenarios).expanduser()
    if not path.is_absolute():
        path = (_ROOT / path).resolve()
    if not path.exists():
        print(f"scenarios file not found: {path}", file=sys.stderr)
        return 2

    scenarios = _load_scenarios(path)
    if args.tag:
        scenarios = [s for s in scenarios if _tag_match(s, args.tag)]

    if args.list:
        for s in scenarios:
            tags = s.get("tags") or {}
            tag_s = ",".join(f"{k}={v}" for k, v in tags.items()) if isinstance(tags, dict) else ""
            print(f"{s.get('label', '')}\t{tag_s}")
        return 0

    selected: list[dict[str, Any]]
    if args.label:
        selected = [s for s in scenarios if s.get("label") == args.label]
        if not selected:
            print(f"unknown label: {args.label}", file=sys.stderr)
            return 2
    elif args.all:
        selected = scenarios
    else:
        print("pass --list, --label ..., or --all", file=sys.stderr)
        return 2

    if args.limit is not None:
        selected = selected[: max(0, args.limit)]

    if not selected:
        print("no scenarios matched", file=sys.stderr)
        return 2

    if not os.environ.get("PARLOT_ENDPOINT"):
        logger.warning("PARLOT_ENDPOINT unset — telemetry will not reach a collector")

    session_ids: list[tuple[str, str]] = []
    failed = 0
    for scenario in selected:
        label = scenario.get("label") or "(unnamed)"
        try:
            sid = await _run_scenario(
                scenario,
                agent_model=args.agent_model,
                persona_model=args.persona_model,
                max_turns=args.max_turns,
            )
            session_ids.append((label, sid))
        except Exception:
            failed += 1
            logger.exception("scenario failed: %s", label)

    print("\n=== summary ===")
    for label, sid in session_ids:
        print(f"{label}\t{sid}")
    if failed:
        print(f"{failed} scenario(s) failed", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        default=str(DEFAULT_SCENARIOS),
        help=f"Scenario YAML path (default: {DEFAULT_SCENARIOS.name})",
    )
    parser.add_argument("--list", action="store_true", help="List scenario labels")
    parser.add_argument("--label", help="Run a single scenario by exact label")
    parser.add_argument("--all", action="store_true", help="Run all matched scenarios")
    parser.add_argument("--tag", help="Filter scenarios by tags key=value")
    parser.add_argument("--limit", type=int, help="Max scenarios to run after filtering")
    parser.add_argument("--max-turns", type=int, default=24, help="Max guest turns per scenario")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--persona-model", default=DEFAULT_PERSONA_MODEL)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
