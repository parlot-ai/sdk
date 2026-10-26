"""STT/TTS link to Parlot turn indices; user + agent turns are minted separately."""

from __future__ import annotations

import time

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import set_span_in_context

from parlot.core.attrs import (
    ATTR_SESSION_ID,
    ATTR_TURN_AGENT_TEXT,
    ATTR_TURN_E2E_LATENCY_S,
    ATTR_TURN_INDEX,
    ATTR_TURN_LLM_TTFT_S,
    ATTR_TURN_PARTICIPANT_ROLE,
    ATTR_TURN_TTS_TTFB_S,
    ATTR_TURN_USER_TEXT,
    SPAN_PARLOT_TURN,
    SPAN_VOICE_STT,
    SPAN_VOICE_TTS,
)
from parlot.core.session import clear_active_session
from parlot.instrumentation.pipecat._processor import PipecatGenAIProcessor
from parlot.instrumentation.pipecat._session import (
    _sessions_by_conversation,
    close_session,
    set_identity,
    set_tracer,
)
from parlot.instrumentation.pipecat.attrs import (
    ATTR_PIPECAT_CONVERSATION_ID,
    ATTR_PIPECAT_METRICS_TTFB,
    ATTR_PIPECAT_TEXT,
    ATTR_PIPECAT_TRANSCRIPT,
    ATTR_PIPECAT_TURN_NUMBER,
    ATTR_PIPECAT_TURN_USER_BOT_LATENCY,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    clear_active_session()
    _sessions_by_conversation.clear()
    yield
    for cid in list(_sessions_by_conversation):
        close_session(cid, reason="test_teardown")
    _sessions_by_conversation.clear()
    clear_active_session()


def _provider() -> tuple[InMemorySpanExporter, TracerProvider]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(PipecatGenAIProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter, provider


def test_stt_tts_emit_separate_user_and_agent_turns() -> None:
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    conv = tracer.start_span("conversation")
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-1")
    turn = tracer.start_span("turn", context=set_span_in_context(conv))
    turn.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-1")
    turn.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)

    stt = tracer.start_span("stt", context=set_span_in_context(turn))
    stt.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "hello there")
    stt.end()

    tts = tracer.start_span("tts", context=set_span_in_context(turn))
    tts.set_attribute(ATTR_PIPECAT_TEXT, "hi friend")
    tts.end()

    turn.end()
    conv.end()

    finished = list(exporter.get_finished_spans())
    stt_span = next(s for s in finished if s.name == SPAN_VOICE_STT)
    tts_span = next(s for s in finished if s.name == SPAN_VOICE_TTS)
    turns = [s for s in finished if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 2

    # STT nests under the agent turn (platform timeline); user turn is utterance-only.
    assert stt_span.attributes[ATTR_SESSION_ID]
    assert stt_span.attributes[ATTR_TURN_INDEX] == 2
    assert stt_span.attributes[ATTR_TURN_USER_TEXT] == "hello there"

    assert tts_span.attributes[ATTR_SESSION_ID] == stt_span.attributes[ATTR_SESSION_ID]
    assert tts_span.attributes[ATTR_TURN_INDEX] == 2
    assert tts_span.attributes[ATTR_TURN_AGENT_TEXT] == "hi friend"

    by_role = {s.attributes[ATTR_TURN_PARTICIPANT_ROLE]: s for s in turns}
    assert by_role["user"].attributes[ATTR_TURN_INDEX] == 1
    assert by_role["user"].attributes[ATTR_TURN_USER_TEXT] == "hello there"
    assert ATTR_TURN_AGENT_TEXT not in (by_role["user"].attributes or {})
    assert by_role["agent"].attributes[ATTR_TURN_INDEX] == 2
    assert by_role["agent"].attributes[ATTR_TURN_AGENT_TEXT] == "hi friend"


def test_agent_greeting_only_gets_agent_turn() -> None:
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    conv = tracer.start_span("conversation")
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-greet")
    turn = tracer.start_span("turn", context=set_span_in_context(conv))
    turn.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-greet")
    turn.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)

    tts = tracer.start_span("tts", context=set_span_in_context(turn))
    tts.set_attribute(ATTR_PIPECAT_TEXT, "How can I assist you today?")
    tts.end()

    turn.end()
    conv.end()

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    assert len(turns) == 1
    assert turns[0].attributes[ATTR_TURN_PARTICIPANT_ROLE] == "agent"
    assert turns[0].attributes[ATTR_TURN_INDEX] == 1
    assert turns[0].attributes[ATTR_TURN_AGENT_TEXT] == "How can I assist you today?"


def test_tool_continuation_agent_flushed_before_next_user() -> None:
    """Agent-only tool follow-up must not invert indices with the next user STT."""
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    t0 = time.time_ns()
    conv = tracer.start_span("conversation", start_time=t0)
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-tool")

    # Native turn 1: user asks + agent "let me check"
    turn1 = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0
    )
    turn1.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-tool")
    turn1.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)

    stt1 = tracer.start_span(
        "stt", context=set_span_in_context(turn1), start_time=t0 + 1_000_000_000
    )
    stt1.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "weather in Miami?")
    stt1.set_attribute("is_final", True)
    stt1.end(end_time=t0 + 1_500_000_000)

    tts1 = tracer.start_span(
        "tts", context=set_span_in_context(turn1), start_time=t0 + 1_600_000_000
    )
    tts1.set_attribute(ATTR_PIPECAT_TEXT, "Let me check on that.")
    tts1.end(end_time=t0 + 2_500_000_000)
    turn1.end(end_time=t0 + 3_000_000_000)

    # Native turn 2: tool result speech with NO user (agent-only), still open
    # when the next user STT arrives — the bug that put T5 before T4.
    turn2 = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0 + 3_100_000_000
    )
    turn2.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-tool")
    turn2.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 2)

    tts2 = tracer.start_span(
        "tts", context=set_span_in_context(turn2), start_time=t0 + 3_200_000_000
    )
    tts2.set_attribute(ATTR_PIPECAT_TEXT, "It's 75 degrees.")
    tts2.end(end_time=t0 + 4_000_000_000)

    # User asks follow-up while turn 2 is still open (agent index reserved).
    stt2 = tracer.start_span(
        "stt", context=set_span_in_context(turn2), start_time=t0 + 4_100_000_000
    )
    stt2.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "Celsius or Fahrenheit?")
    stt2.set_attribute("is_final", True)
    stt2.end(end_time=t0 + 4_500_000_000)

    tts3 = tracer.start_span(
        "tts", context=set_span_in_context(turn2), start_time=t0 + 4_600_000_000
    )
    tts3.set_attribute(ATTR_PIPECAT_TEXT, "That's in Fahrenheit.")
    tts3.end(end_time=t0 + 5_200_000_000)
    turn2.end(end_time=t0 + 5_500_000_000)
    conv.end(end_time=t0 + 5_600_000_000)

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    ordered = sorted(turns, key=lambda s: int(s.attributes[ATTR_TURN_INDEX]))
    roles = [s.attributes[ATTR_TURN_PARTICIPANT_ROLE] for s in ordered]
    texts = [
        (s.attributes.get(ATTR_TURN_USER_TEXT) or s.attributes.get(ATTR_TURN_AGENT_TEXT) or "")
        for s in ordered
    ]
    indexes = [int(s.attributes[ATTR_TURN_INDEX]) for s in ordered]

    assert indexes == sorted(indexes)
    # Wall-clock order must match turn-index order (no T5-before-T4).
    by_time = sorted(turns, key=lambda s: s.start_time or 0)
    assert [int(s.attributes[ATTR_TURN_INDEX]) for s in by_time] == indexes

    assert "weather in Miami?" in texts
    assert "Let me check on that." in texts
    assert "It's 75 degrees." in texts
    assert "Celsius or Fahrenheit?" in texts
    assert "That's in Fahrenheit." in texts
    # User follow-up index must be greater than the tool-result agent index.
    deg_idx = next(
        int(s.attributes[ATTR_TURN_INDEX])
        for s in turns
        if (s.attributes.get(ATTR_TURN_AGENT_TEXT) or "") == "It's 75 degrees."
    )
    celsius_idx = next(
        int(s.attributes[ATTR_TURN_INDEX])
        for s in turns
        if (s.attributes.get(ATTR_TURN_USER_TEXT) or "") == "Celsius or Fahrenheit?"
    )
    assert celsius_idx > deg_idx
    assert roles.count("user") >= 2
    assert roles.count("agent") >= 3


def test_turn_bounds_follow_stt_and_llm_tts_windows() -> None:
    """User/agent remints use STT vs LLM+TTS clocks — not the shared native turn."""
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    t0 = time.time_ns()
    conv = tracer.start_span("conversation", start_time=t0)
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-timing")
    turn = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0
    )
    turn.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-timing")
    turn.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)
    turn.set_attribute(ATTR_PIPECAT_TURN_USER_BOT_LATENCY, 0.85)

    stt_start = t0 + 1_000_000_000
    stt_end = t0 + 1_400_000_000
    stt = tracer.start_span(
        "stt", context=set_span_in_context(turn), start_time=stt_start
    )
    stt.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "hello")
    stt.end(end_time=stt_end)

    llm_start = t0 + 1_450_000_000
    llm_end = t0 + 1_900_000_000
    llm = tracer.start_span(
        "llm", context=set_span_in_context(turn), start_time=llm_start
    )
    llm.set_attribute("gen_ai.request.model", "gpt-4o-mini")
    llm.set_attribute(ATTR_PIPECAT_METRICS_TTFB, 0.3)
    llm.set_attribute("output", "hi there")
    llm.end(end_time=llm_end)

    tts_start = t0 + 1_920_000_000
    tts_end = t0 + 2_200_000_000
    tts = tracer.start_span(
        "tts", context=set_span_in_context(turn), start_time=tts_start
    )
    tts.set_attribute(ATTR_PIPECAT_TEXT, "hi there")
    tts.set_attribute(ATTR_PIPECAT_METRICS_TTFB, 0.25)
    tts.end(end_time=tts_end)

    # Native turn stays open much longer (bot speaking + idle) — must not leak.
    turn.end(end_time=t0 + 10_000_000_000)
    conv.end(end_time=t0 + 10_000_000_000)

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    by_role = {s.attributes[ATTR_TURN_PARTICIPANT_ROLE]: s for s in turns}
    user = by_role["user"]
    agent = by_role["agent"]

    assert user.start_time == stt_start
    assert user.end_time == stt_end
    assert agent.start_time == llm_start
    assert agent.end_time == tts_end
    assert agent.attributes[ATTR_TURN_LLM_TTFT_S] == pytest.approx(0.3)
    assert agent.attributes[ATTR_TURN_TTS_TTFB_S] == pytest.approx(0.25)
    assert agent.attributes[ATTR_TURN_E2E_LATENCY_S] == pytest.approx(0.85)
    # Reminted windows must stay far shorter than the 10s native turn.
    assert (user.end_time - user.start_time) < 1_000_000_000
    assert (agent.end_time - agent.start_time) < 2_000_000_000


def test_premature_native_turn_still_mints_agent_after_stt_user() -> None:
    """Native turn ends before STT/TTS; reserved agent must still emit on TTS.

    Reproduces staging gap: Pipecat Turn N closes in ~80ms, user STT mints and
    reserves agent N+1, reply TTS lands with no open native turn — previously
    orphan/flush bailed on open_user_turn_index and the utterance was lost.
    """
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    t0 = time.time_ns()
    conv = tracer.start_span("conversation", start_time=t0)
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")

    # Spurious short native turn (ends before speech finishes).
    turn = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0
    )
    turn.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    turn.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 3)
    turn.end(end_time=t0 + 80_000_000)

    # STT final + agent reply run with no open native turn.
    stt = tracer.start_span("stt", start_time=t0 + 200_000_000)
    stt.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    stt.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 3)
    stt.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "Sounds perfect.")
    stt.set_attribute("is_final", True)
    stt.end(end_time=t0 + 400_000_000)

    llm = tracer.start_span("llm", start_time=t0 + 450_000_000)
    llm.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    llm.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 3)
    llm.set_attribute(
        "output", "It really does! Would you like to know anything else?"
    )
    llm.end(end_time=t0 + 800_000_000)

    tts = tracer.start_span("tts", start_time=t0 + 850_000_000)
    tts.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    tts.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 3)
    tts.set_attribute(
        ATTR_PIPECAT_TEXT, "It really does! Would you like to know anything else?"
    )
    tts.end(end_time=t0 + 2_000_000_000)

    # Next exchange must not steal the prior agent slot.
    turn4 = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0 + 2_100_000_000
    )
    turn4.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-premature")
    turn4.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 4)
    stt2 = tracer.start_span(
        "stt", context=set_span_in_context(turn4), start_time=t0 + 2_200_000_000
    )
    stt2.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "All. Thank you.")
    stt2.set_attribute("is_final", True)
    stt2.end(end_time=t0 + 2_500_000_000)
    tts2 = tracer.start_span(
        "tts", context=set_span_in_context(turn4), start_time=t0 + 2_600_000_000
    )
    tts2.set_attribute(ATTR_PIPECAT_TEXT, "You're welcome! Have a great day!")
    tts2.end(end_time=t0 + 3_200_000_000)
    turn4.end(end_time=t0 + 3_300_000_000)
    conv.end(end_time=t0 + 3_400_000_000)

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    ordered = sorted(turns, key=lambda s: int(s.attributes[ATTR_TURN_INDEX]))
    by_text = {
        (
            s.attributes.get(ATTR_TURN_USER_TEXT)
            or s.attributes.get(ATTR_TURN_AGENT_TEXT)
            or ""
        ): int(s.attributes[ATTR_TURN_INDEX])
        for s in ordered
    }
    assert "Sounds perfect." in by_text
    assert "It really does! Would you like to know anything else?" in by_text
    assert "All. Thank you." in by_text
    assert "You're welcome! Have a great day!" in by_text
    assert (
        by_text["It really does! Would you like to know anything else?"]
        == by_text["Sounds perfect."] + 1
    )
    assert by_text["All. Thank you."] > by_text[
        "It really does! Would you like to know anything else?"
    ]


def test_empty_late_tts_does_not_burn_agent_index() -> None:
    """TTS with no text after a closed turn must not permanently burn an index."""
    exporter, provider = _provider()
    tracer = provider.get_tracer("test")
    set_tracer(tracer)
    set_identity("pipecat-test", "0.1.0")

    t0 = time.time_ns()
    conv = tracer.start_span("conversation", start_time=t0)
    conv.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-empty-tts")

    turn1 = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0
    )
    turn1.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-empty-tts")
    turn1.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)
    tts1 = tracer.start_span(
        "tts", context=set_span_in_context(turn1), start_time=t0 + 100_000_000
    )
    tts1.set_attribute(ATTR_PIPECAT_TEXT, "Hello.")
    tts1.end(end_time=t0 + 500_000_000)
    turn1.end(end_time=t0 + 600_000_000)

    # Late empty TTS (no transcript attr) after native turn closed.
    empty = tracer.start_span("tts", start_time=t0 + 700_000_000)
    empty.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-empty-tts")
    empty.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 1)
    empty.end(end_time=t0 + 800_000_000)

    turn2 = tracer.start_span(
        "turn", context=set_span_in_context(conv), start_time=t0 + 900_000_000
    )
    turn2.set_attribute(ATTR_PIPECAT_CONVERSATION_ID, "conv-empty-tts")
    turn2.set_attribute(ATTR_PIPECAT_TURN_NUMBER, 2)
    stt = tracer.start_span(
        "stt", context=set_span_in_context(turn2), start_time=t0 + 1_000_000_000
    )
    stt.set_attribute(ATTR_PIPECAT_TRANSCRIPT, "Hi")
    stt.set_attribute("is_final", True)
    stt.end(end_time=t0 + 1_200_000_000)
    tts2 = tracer.start_span(
        "tts", context=set_span_in_context(turn2), start_time=t0 + 1_300_000_000
    )
    tts2.set_attribute(ATTR_PIPECAT_TEXT, "Hey there.")
    tts2.end(end_time=t0 + 1_800_000_000)
    turn2.end(end_time=t0 + 1_900_000_000)
    conv.end(end_time=t0 + 2_000_000_000)

    turns = [s for s in exporter.get_finished_spans() if s.name == SPAN_PARLOT_TURN]
    indexes = sorted(int(s.attributes[ATTR_TURN_INDEX]) for s in turns)
    # Greeting agent=1, user=2, agent=3 — no gap from the empty late TTS.
    assert indexes == [1, 2, 3]
