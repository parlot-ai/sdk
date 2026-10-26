# parlot-instrumentation-pipecat

Parlot OpenTelemetry instrumentation for [Pipecat](https://github.com/pipecat-ai/pipecat)
production voice AI agents.

Emits Parlot’s Conversation Contract (`parlot.session`, `parlot.turn`, GenAI/voice spans) so
Pipecat sessions show up in the same debugger as LiveKit and LangGraph.

## Install

```bash
pip install parlot-instrumentation-pipecat
# or: pip install "parlot[pipecat]"
```

## Requirements

For `parlot.turn` (user/agent transcript on the timeline), the pipeline **must** include
`LLMUserAggregator` and `LLMAssistantAggregator` — typically via `LLMContextAggregatorPair`.
Parlot does not create them. Put the assistant aggregator **after** `transport.output()`.

Call `parlotize()` **before** building aggregators so handlers auto-wire. If they already
exist, call `attach_aggregators(user, assistant)`. Without aggregators you may still get
session + STT/LLM/TTS spans, but not contract turns.

Your own aggregator event handlers and `observers=[...]` keep working — Parlot appends
alongside them.

## Instrument

```python
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from parlot.instrumentation.pipecat import attach_aggregators, parlotize

parlotize("my-pipecat-agent", version="0.1.0")

context_aggregator = LLMContextAggregatorPair(context)
# attach_aggregators(...) only if the pair was built before parlotize()

pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    llm,
    tts,
    transport.output(),
    context_aggregator.assistant(),
])

worker = PipelineWorker(
    pipeline,
    params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    enable_tracing=True,
    enable_turn_tracking=True,
)
```

```bash
export PARLOT_ENDPOINT=https://ingest.parlot.ai
export PARLOT_API_KEY=<org-scoped-key>
```

## Example

See [`examples/pipecat/minimal-voice/`](https://github.com/parlot-ai/sdk/tree/main/examples/pipecat/minimal-voice) (adapted from Pipecat's [open-telemetry/langfuse](https://github.com/pipecat-ai/pipecat-examples/tree/main/open-telemetry/langfuse) demo).

## Docs

- [Pipecat guide](https://parlot.ai/docs/sdk/guides/pipecat)
- [Concepts](https://parlot.ai/docs/sdk/get-started/concepts)
