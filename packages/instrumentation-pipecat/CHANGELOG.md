# Changelog

## [0.1.11](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.10...instrumentation-pipecat-v0.1.11) (2026-11-09)


### Bug Fixes

* rename recording_webhook_error to recording_error ([#152](https://github.com/parlot-ai/sdk/issues/152)) ([8efcf12](https://github.com/parlot-ai/sdk/commit/8efcf1258f4a995a4281bfc1afc218cced674c38))

## [0.1.10](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.9...instrumentation-pipecat-v0.1.10) (2026-11-09)


### Bug Fixes

* **recording:** stamp concrete upload-grant denials and improve anchors ([#148](https://github.com/parlot-ai/sdk/issues/148)) ([b00a62b](https://github.com/parlot-ai/sdk/commit/b00a62bf5a4aaf3be400705e30658d0f55d90997))

## [0.1.9](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.8...instrumentation-pipecat-v0.1.9) (2026-11-05)


### Documentation

* **pipecat:** align examples with minimal-voice bot implementation ([#142](https://github.com/parlot-ai/sdk/issues/142)) ([69904fc](https://github.com/parlot-ai/sdk/commit/69904fc552238f889437df0a6b40511abea7ce11))

## [0.1.8](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.7...instrumentation-pipecat-v0.1.8) (2026-10-28)


### Bug Fixes

* **core:** default OTel service.name to agent_id ([#133](https://github.com/parlot-ai/sdk/issues/133)) ([95cbaec](https://github.com/parlot-ai/sdk/commit/95cbaec52eba066a71876978d5d29edf13c156e7))

## [0.1.7](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.6...instrumentation-pipecat-v0.1.7) (2026-10-27)


### Bug Fixes

* **pipecat:** rewind turn_count when clearing unused reservations ([#131](https://github.com/parlot-ai/sdk/issues/131)) ([e50c7cf](https://github.com/parlot-ai/sdk/commit/e50c7cf510ef71787ec96ff64b7c6f64397013a4))

## [0.1.6](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.5...instrumentation-pipecat-v0.1.6) (2026-10-26)


### Features

* **pipecat:** attach_aggregators and document aggregator requirement ([#128](https://github.com/parlot-ai/sdk/issues/128)) ([3e2e628](https://github.com/parlot-ai/sdk/commit/3e2e628c712969063d835c8725871809cd386af5))


### Bug Fixes

* **pipecat:** mint parlot.turn from context-aggregator events ([#125](https://github.com/parlot-ai/sdk/issues/125)) ([cfe1b8c](https://github.com/parlot-ai/sdk/commit/cfe1b8cea03b2009e35b8dbd140e54ef4869ec5e))
* **pipecat:** restore e2e latency and reserve turns on started events ([#127](https://github.com/parlot-ai/sdk/issues/127)) ([95d3ffb](https://github.com/parlot-ai/sdk/commit/95d3ffbb8511d43d7d5126d95ab827f72881e71c))

## [0.1.5](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.4...instrumentation-pipecat-v0.1.5) (2026-10-25)


### Bug Fixes

* **pipecat:** await final segment upload before recording complete ([#120](https://github.com/parlot-ai/sdk/issues/120)) ([38dba4d](https://github.com/parlot-ai/sdk/commit/38dba4d0d5dde413b5fd100ab7375d662494c33e))

## [0.1.4](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.3...instrumentation-pipecat-v0.1.4) (2026-10-25)


### Features

* frame packages and docs around voice AI agents on LiveKit, Pipecat, and LangGraph ([#115](https://github.com/parlot-ai/sdk/issues/115)) ([7f6366b](https://github.com/parlot-ai/sdk/commit/7f6366bea87361bbfb8ec4df4371adecf89f6c42))

## [0.1.3](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.2...instrumentation-pipecat-v0.1.3) (2026-10-25)


### Features

* **pipecat:** add framework-agnostic session recording ([#111](https://github.com/parlot-ai/sdk/issues/111)) ([1e5c036](https://github.com/parlot-ai/sdk/commit/1e5c036a161d4d1f51cf4d9a406db926970b4575))

## [0.1.2](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.1...instrumentation-pipecat-v0.1.2) (2026-10-23)


### Bug Fixes

* **instrumentation-pipecat:** point example link at GitHub and use PyPI in minimal-voice ([#105](https://github.com/parlot-ai/sdk/issues/105)) ([7d9b1b9](https://github.com/parlot-ai/sdk/commit/7d9b1b9d7df8dc8d38589e7fe3cc585237e20313))

## [0.1.1](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.1.0...instrumentation-pipecat-v0.1.1) (2026-10-23)


### Features

* **pipecat:** add Conversation Contract instrumentation adapter ([#102](https://github.com/parlot-ai/sdk/issues/102)) ([807ceb5](https://github.com/parlot-ai/sdk/commit/807ceb5f0a0b8057bb4705e4d5db4f1fa72eb286))

## [0.1.0](https://github.com/parlot-ai/sdk/compare/instrumentation-pipecat-v0.0.0...instrumentation-pipecat-v0.1.0) (2026-10-22)


### Features

* Pipecat Conversation Contract instrumentation via OpenTelemetry remap
