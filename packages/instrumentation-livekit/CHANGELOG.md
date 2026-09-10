# Changelog

## [0.3.0](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.2.1...instrumentation-livekit-v0.3.0) (2026-09-10)


### ⚠ BREAKING CHANGES

* import and call parlotize() instead of configure().

### Features

* rename configure() to parlotize() ([#54](https://github.com/parlot-ai/sdk/issues/54)) ([30d4579](https://github.com/parlot-ai/sdk/commit/30d4579922043d2c508d48f15eb80a3632e8ff6f))

## [0.2.1](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.2.0...instrumentation-livekit-v0.2.1) (2026-09-07)


### Features

* **core:** implement multi-layer SDK versioning and remove diagnostics ([#47](https://github.com/parlot-ai/sdk/issues/47)) ([2e021bb](https://github.com/parlot-ai/sdk/commit/2e021bb2495ce1ae08e7d4aebb497c789e9e154b))


### Bug Fixes

* **livekit:** mutate readable span attributes safely and mock simulation job context ([#45](https://github.com/parlot-ai/sdk/issues/45)) ([36175c6](https://github.com/parlot-ai/sdk/commit/36175c675b25c1f88a370c821890bb9f40ffebc9))
* log descriptive sdk errors without dumping tracebacks ([#46](https://github.com/parlot-ai/sdk/issues/46)) ([06275e2](https://github.com/parlot-ai/sdk/commit/06275e2c6110295739e0971976d2fe2943457d14))


### Documentation

* generate shared configure() API from Python docstrings ([#41](https://github.com/parlot-ai/sdk/issues/41)) ([8ae405f](https://github.com/parlot-ai/sdk/commit/8ae405feab794e6f39e41146b91b73daaa95cf35))

## [0.2.0](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.1.1...instrumentation-livekit-v0.2.0) (2026-09-03)


### ⚠ BREAKING CHANGES

* ParlotRuntimeContext.org_id and the org_id OTel attribute are now tenant_id.
* introduce ParlotContext for SDK instance state ([#32](https://github.com/parlot-ai/sdk/issues/32))

### Features

* **livekit:** stamp session.recording.disabled_reason when egress skipped ([#30](https://github.com/parlot-ai/sdk/issues/30)) ([fc1e64c](https://github.com/parlot-ai/sdk/commit/fc1e64c860c4105bd1e3eb9f646969e05d68848a))


### Bug Fixes

* **livekit:** detect SIP kind and dial softphone supervisors ([#37](https://github.com/parlot-ai/sdk/issues/37)) ([c45db73](https://github.com/parlot-ai/sdk/commit/c45db7324fbe5120db2544d4f678eeb5f226fe8c))
* **livekit:** stamp agent turn media from metrics only ([#39](https://github.com/parlot-ai/sdk/issues/39)) ([e61dd22](https://github.com/parlot-ai/sdk/commit/e61dd22f743bfd0a404ea4a500f7b962e82fa26e))
* **livekit:** support lk agent --dev watch parent ([#33](https://github.com/parlot-ai/sdk/issues/33)) ([eac79b9](https://github.com/parlot-ai/sdk/commit/eac79b9034a8acc0b28f228fc8392e46fbe272f2))


### Documentation

* use lk agent dev in LiveKit example READMEs ([#28](https://github.com/parlot-ai/sdk/issues/28)) ([397de21](https://github.com/parlot-ai/sdk/commit/397de217e7f48ed52d881a3274d55fed807dbc22))


### Code Refactoring

* introduce ParlotContext for SDK instance state ([#32](https://github.com/parlot-ai/sdk/issues/32)) ([8998bfa](https://github.com/parlot-ai/sdk/commit/8998bfa6f5b4aa75243a8b224b06631a9a61109b))
* rename bootstrap and OTel org_id to tenant_id ([#34](https://github.com/parlot-ai/sdk/issues/34)) ([cccb6a6](https://github.com/parlot-ai/sdk/commit/cccb6a6766555a6a11997d51208eed4218e00e6d))

## [0.1.1](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.1.0...instrumentation-livekit-v0.1.1) (2026-08-25)


### Features

* **livekit:** accept lk.pii.* attribute keys from Agents 1.7 ([#21](https://github.com/parlot-ai/sdk/issues/21)) ([2853a40](https://github.com/parlot-ai/sdk/commit/2853a40ff568af4a10159aad94c31b129ad1bc37))
* multi-framework GenAI vocabulary + LangGraph configure() ([#3](https://github.com/parlot-ai/sdk/issues/3)) ([8d5b3a8](https://github.com/parlot-ai/sdk/commit/8d5b3a8e7ccece33f09b4b31a424721eb54286ef))
* prepare SDK packages and workflows for public PyPI release ([#15](https://github.com/parlot-ai/sdk/issues/15)) ([2c02e09](https://github.com/parlot-ai/sdk/commit/2c02e09960726605b937578b9f095f77f5a7f73a))
* resolve generative AI content capture from telemetry bootstrap ([#12](https://github.com/parlot-ai/sdk/issues/12)) ([e3be83b](https://github.com/parlot-ai/sdk/commit/e3be83b14235f0b7cb718e9f97fb0dc4188e423d))
* session log capture handler and configure(capture_logs=) ([#8](https://github.com/parlot-ai/sdk/issues/8)) ([b054eb1](https://github.com/parlot-ai/sdk/commit/b054eb164a4a39bcfc561690a4bf703407fbb52f))


### Bug Fixes

* LangGraph timeline text without synthetic companions ([#5](https://github.com/parlot-ai/sdk/issues/5)) ([95675c0](https://github.com/parlot-ai/sdk/commit/95675c0029867ecf4338a32c041f78e5624320b3))


### Documentation

* merge LiveKit guides and extract agnostic Concepts ([#6](https://github.com/parlot-ai/sdk/issues/6)) ([dfe6247](https://github.com/parlot-ai/sdk/commit/dfe62471afc521db16d0bc1a034ebcb066900a7e))
* note livekit conversation_id equals session_id for now ([#7](https://github.com/parlot-ai/sdk/issues/7)) ([393eaf2](https://github.com/parlot-ai/sdk/commit/393eaf2c94f7e71ca4bab2eb100231ff530e8545))
* rewrite README, Quick Start, and PyPI package copy for voice GTM ([#22](https://github.com/parlot-ai/sdk/issues/22)) ([5066319](https://github.com/parlot-ai/sdk/commit/5066319503d03060c783f9a3622bd30b50b05e59))

## [0.1.0](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.0.0...instrumentation-livekit-v0.1.0) (2026-05-15)


### Features

* LiveKit span processor with `platform.ref.*` stamping for session resolve
