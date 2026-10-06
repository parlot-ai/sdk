# Changelog

## [0.4.5](https://github.com/parlot-ai/sdk/compare/core-v0.4.4...core-v0.4.5) (2026-10-06)


### Features

* **livekit:** retry OTLP flush before session close ([#90](https://github.com/parlot-ai/sdk/issues/90)) ([d32e603](https://github.com/parlot-ai/sdk/commit/d32e6031d8bd5d1a74584658b617f62edc659abe))


### Documentation

* Cost CSV export and callout/link doc polish ([#88](https://github.com/parlot-ai/sdk/issues/88)) ([eadfcfd](https://github.com/parlot-ai/sdk/commit/eadfcfdc09880689f2426f37a4b06b75d0d9b5bb))

## [0.4.4](https://github.com/parlot-ai/sdk/compare/core-v0.4.3...core-v0.4.4) (2026-10-04)


### Bug Fixes

* include METRIC_ constants in attrs.ts sync test ([#86](https://github.com/parlot-ai/sdk/issues/86)) ([e10e7a2](https://github.com/parlot-ai/sdk/commit/e10e7a283d2954561b741a0790a36c99a9250716))

## [0.4.3](https://github.com/parlot-ai/sdk/compare/core-v0.4.2...core-v0.4.3) (2026-10-04)


### Features

* **core:** add session LLM/STT/TTS cost attribute constants ([#80](https://github.com/parlot-ai/sdk/issues/80)) ([76f0144](https://github.com/parlot-ai/sdk/commit/76f0144d43476ab7bf309c676e2422ecac92906e))
* **core:** add session STT/TTS usage attribute constants ([#82](https://github.com/parlot-ai/sdk/issues/82)) ([978307c](https://github.com/parlot-ai/sdk/commit/978307c8fbaa02b4c8ac9e4aa83b0e57a556d266))

## [0.4.2](https://github.com/parlot-ai/sdk/compare/core-v0.4.1...core-v0.4.2) (2026-09-29)


### Bug Fixes

* log clear errors when Parlot endpoint or API key is misconfigured ([#74](https://github.com/parlot-ai/sdk/issues/74)) ([345f48b](https://github.com/parlot-ai/sdk/commit/345f48b8af6e2d929800f225bdb1a2190da97a3a))


### Documentation

* simplify repo and PyPI READMEs for get-started ([#77](https://github.com/parlot-ai/sdk/issues/77)) ([279a254](https://github.com/parlot-ai/sdk/commit/279a2549b4bf78a4e0dd5117f9def389bcf53ae3))

## [0.4.1](https://github.com/parlot-ai/sdk/compare/core-v0.4.0...core-v0.4.1) (2026-09-17)


### Bug Fixes

* bound SessionTopology handoff and agent-chain memory growth ([#67](https://github.com/parlot-ai/sdk/issues/67)) ([ae474ce](https://github.com/parlot-ai/sdk/commit/ae474cebe1caddb0e502da436590bc8533428c52))
* **livekit:** sticky session id for post-close evaluation LLM spans ([#69](https://github.com/parlot-ai/sdk/issues/69)) ([a0475b7](https://github.com/parlot-ai/sdk/commit/a0475b7d88733ea4e035b4d62c50c6ddd353077a))

## [0.4.0](https://github.com/parlot-ai/sdk/compare/core-v0.3.1...core-v0.4.0) (2026-09-14)


### ⚠ BREAKING CHANGES

* require agent_id on parlotize() ([#63](https://github.com/parlot-ai/sdk/issues/63))

### Features

* require agent_id on parlotize() ([#63](https://github.com/parlot-ai/sdk/issues/63)) ([ce42357](https://github.com/parlot-ai/sdk/commit/ce4235730b514606e0cfe7f08aa61b78b408d75b))

## [0.3.1](https://github.com/parlot-ai/sdk/compare/core-v0.3.0...core-v0.3.1) (2026-09-13)


### Bug Fixes

* **livekit:** mint agent identity when parlotize omits agent_id ([#62](https://github.com/parlot-ai/sdk/issues/62)) ([b14fe0d](https://github.com/parlot-ai/sdk/commit/b14fe0d3b0848b752b0d4f487a4af71595bff1ea))

## [0.3.0](https://github.com/parlot-ai/sdk/compare/core-v0.2.1...core-v0.3.0) (2026-09-10)


### ⚠ BREAKING CHANGES

* import and call parlotize() instead of configure().

### Features

* **core:** export session logs as OTLP Logs protobuf ([#52](https://github.com/parlot-ai/sdk/issues/52)) ([27497dc](https://github.com/parlot-ai/sdk/commit/27497dc51127cb05f384d3bcec8ac82801005bab))
* rename configure() to parlotize() ([#54](https://github.com/parlot-ai/sdk/issues/54)) ([30d4579](https://github.com/parlot-ai/sdk/commit/30d4579922043d2c508d48f15eb80a3632e8ff6f))

## [0.2.1](https://github.com/parlot-ai/sdk/compare/core-v0.2.0...core-v0.2.1) (2026-09-07)


### Features

* **core:** implement multi-layer SDK versioning and remove diagnostics ([#47](https://github.com/parlot-ai/sdk/issues/47)) ([2e021bb](https://github.com/parlot-ai/sdk/commit/2e021bb2495ce1ae08e7d4aebb497c789e9e154b))


### Bug Fixes

* **livekit:** mutate readable span attributes safely and mock simulation job context ([#45](https://github.com/parlot-ai/sdk/issues/45)) ([36175c6](https://github.com/parlot-ai/sdk/commit/36175c675b25c1f88a370c821890bb9f40ffebc9))
* log descriptive sdk errors without dumping tracebacks ([#46](https://github.com/parlot-ai/sdk/issues/46)) ([06275e2](https://github.com/parlot-ai/sdk/commit/06275e2c6110295739e0971976d2fe2943457d14))


### Documentation

* generate shared configure() API from Python docstrings ([#41](https://github.com/parlot-ai/sdk/issues/41)) ([8ae405f](https://github.com/parlot-ai/sdk/commit/8ae405feab794e6f39e41146b91b73daaa95cf35))

## [0.2.0](https://github.com/parlot-ai/sdk/compare/core-v0.1.1...core-v0.2.0) (2026-09-03)


### ⚠ BREAKING CHANGES

* ParlotRuntimeContext.org_id and the org_id OTel attribute are now tenant_id.
* introduce ParlotContext for SDK instance state ([#32](https://github.com/parlot-ai/sdk/issues/32))

### Features

* **livekit:** stamp session.recording.disabled_reason when egress skipped ([#30](https://github.com/parlot-ai/sdk/issues/30)) ([fc1e64c](https://github.com/parlot-ai/sdk/commit/fc1e64c860c4105bd1e3eb9f646969e05d68848a))


### Code Refactoring

* introduce ParlotContext for SDK instance state ([#32](https://github.com/parlot-ai/sdk/issues/32)) ([8998bfa](https://github.com/parlot-ai/sdk/commit/8998bfa6f5b4aa75243a8b224b06631a9a61109b))
* rename bootstrap and OTel org_id to tenant_id ([#34](https://github.com/parlot-ai/sdk/issues/34)) ([cccb6a6](https://github.com/parlot-ai/sdk/commit/cccb6a6766555a6a11997d51208eed4218e00e6d))

## [0.1.1](https://github.com/parlot-ai/sdk/compare/core-v0.1.0...core-v0.1.1) (2026-08-25)


### Features

* add healthcare and drive-thru LiveKit examples with shared persona sim ([2764d01](https://github.com/parlot-ai/sdk/commit/2764d01a9ad4926caf08552d3cc82b1d5a73dfc0))
* honor per-agent log min level from bootstrap ([#13](https://github.com/parlot-ai/sdk/issues/13)) ([bc3996c](https://github.com/parlot-ai/sdk/commit/bc3996ca98052b5b90ad35f24065621a118851fd))
* multi-framework GenAI vocabulary + LangGraph configure() ([#3](https://github.com/parlot-ai/sdk/issues/3)) ([8d5b3a8](https://github.com/parlot-ai/sdk/commit/8d5b3a8e7ccece33f09b4b31a424721eb54286ef))
* prepare SDK packages and workflows for public PyPI release ([#15](https://github.com/parlot-ai/sdk/issues/15)) ([2c02e09](https://github.com/parlot-ai/sdk/commit/2c02e09960726605b937578b9f095f77f5a7f73a))
* resolve generative AI content capture from telemetry bootstrap ([#12](https://github.com/parlot-ai/sdk/issues/12)) ([e3be83b](https://github.com/parlot-ai/sdk/commit/e3be83b14235f0b7cb718e9f97fb0dc4188e423d))
* session log capture handler and configure(capture_logs=) ([#8](https://github.com/parlot-ai/sdk/issues/8)) ([b054eb1](https://github.com/parlot-ai/sdk/commit/b054eb164a4a39bcfc561690a4bf703407fbb52f))


### Bug Fixes

* flush remaining session logs on shutdown ([#10](https://github.com/parlot-ai/sdk/issues/10)) ([8bc49c6](https://github.com/parlot-ai/sdk/commit/8bc49c60f9a331f4c23fca79f1e4321321440c0e))


### Documentation

* rewrite README, Quick Start, and PyPI package copy for voice GTM ([#22](https://github.com/parlot-ai/sdk/issues/22)) ([5066319](https://github.com/parlot-ai/sdk/commit/5066319503d03060c783f9a3622bd30b50b05e59))
* update SDK API documentation ([#18](https://github.com/parlot-ai/sdk/issues/18)) ([84fe32f](https://github.com/parlot-ai/sdk/commit/84fe32f38bdec056c735dc8f15296bb1d7301c9d))
