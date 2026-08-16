# Changelog

## [0.1.1](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.1.0...instrumentation-livekit-v0.1.1) (2026-08-16)


### Features

* multi-framework GenAI vocabulary + LangGraph configure() ([#3](https://github.com/parlot-ai/sdk/issues/3)) ([8d5b3a8](https://github.com/parlot-ai/sdk/commit/8d5b3a8e7ccece33f09b4b31a424721eb54286ef))
* resolve generative AI content capture from telemetry bootstrap ([#12](https://github.com/parlot-ai/sdk/issues/12)) ([e3be83b](https://github.com/parlot-ai/sdk/commit/e3be83b14235f0b7cb718e9f97fb0dc4188e423d))
* session log capture handler and configure(capture_logs=) ([#8](https://github.com/parlot-ai/sdk/issues/8)) ([b054eb1](https://github.com/parlot-ai/sdk/commit/b054eb164a4a39bcfc561690a4bf703407fbb52f))


### Bug Fixes

* LangGraph timeline text without synthetic companions ([#5](https://github.com/parlot-ai/sdk/issues/5)) ([95675c0](https://github.com/parlot-ai/sdk/commit/95675c0029867ecf4338a32c041f78e5624320b3))


### Documentation

* merge LiveKit guides and extract agnostic Concepts ([#6](https://github.com/parlot-ai/sdk/issues/6)) ([dfe6247](https://github.com/parlot-ai/sdk/commit/dfe62471afc521db16d0bc1a034ebcb066900a7e))
* note livekit conversation_id equals session_id for now ([#7](https://github.com/parlot-ai/sdk/issues/7)) ([393eaf2](https://github.com/parlot-ai/sdk/commit/393eaf2c94f7e71ca4bab2eb100231ff530e8545))

## [0.1.0](https://github.com/parlot-ai/sdk/compare/instrumentation-livekit-v0.0.0...instrumentation-livekit-v0.1.0) (2026-05-15)


### Features

* LiveKit span processor with `platform.ref.*` stamping for session resolve
