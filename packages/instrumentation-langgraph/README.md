# parlot-instrumentation-langgraph

MIT OpenTelemetry instrumentation for **LangGraph / LangChain** agents — the text/webchat path into [Parlot](https://parlot.ai).

Parlot’s lead product is **production voice AI observability** on LiveKit. Use this package when you already run voice **and** want the **same debugger** for LangGraph / LangChain sessions (same turn model — not a separate observability product). Prefer [`parlot-instrumentation-livekit`](https://pypi.org/project/parlot-instrumentation-livekit/) for voice agents.

```bash
pip install parlot-instrumentation-langgraph
# or: uv add parlot-instrumentation-langgraph
# or: pip install "parlot[langgraph]"
```

```python
from parlot.instrumentation.langgraph import parlotize

parlotize("support-bot", version="0.1.0", channel="webchat")

# Normal LangGraph usage — no per-call callbacks required
graph.invoke(
    {"messages": [("user", "Hello")]},
    config={"configurable": {"thread_id": "demo-1"}},
)
```

If `thread_id` is not provided, Parlot mints one automatically (`anon-…`) so
contract spans still attach to a session.

Pass `channel` (e.g. `webchat`, `sms`) when LangGraph owns the session so
ingest does not assume voice. Optional `modality` overrides the default
derived from channel (`webchat`/`sms`/`whatsapp` → text, `voice` → voice).

Set `PARLOT_ENDPOINT` and `PARLOT_API_KEY`. Generative AI content capture
(message bodies / tool payloads; default on) is documented in
[Concepts](https://parlot.ai/docs/concepts#generative-ai-content-capture).
Override with `parlotize(capture_genai_content=False)`.

Session application logs (Python `logging`, default on) follow Settings → Logs /
`parlotize(capture_logs=…, log_level=…)`. Not `print()`. Treat content like stdout for PII.

When used inside a LiveKit voice agent that already called
`parlot.instrumentation.livekit.parlotize("…")`, this package nests GenAI
operational spans under the active LiveKit session and does **not** emit
duplicate `parlot.session` / `parlot.turn` spans — LiveKit owns channel and
modality. Call LangGraph `parlotize("…")` as well (same or related id).

**Docs:** [LangGraph guide](https://parlot.ai/docs/guides/langgraph) · [Concepts](https://parlot.ai/docs/concepts) · [parlot.ai](https://parlot.ai)
