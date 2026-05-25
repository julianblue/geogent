# Changelog

## [0.4.0](https://github.com/julianblue/geogent/compare/geogent-agent-v0.3.0...geogent-agent-v0.4.0) (2026-05-25)


### Features

* **backend:** agriculture raster compute — zonal stats + seasonal time-series ([fce034a](https://github.com/julianblue/geogent/commit/fce034a705d16eb493854ebb142b7e66e563f7ac))


### Bug Fixes

* address PR review correctness feedback ([2e333dc](https://github.com/julianblue/geogent/commit/2e333dcab0aae18f1788c0338958877897dfb066))
* **agent:** drop hardcoded service password default from source ([821bd63](https://github.com/julianblue/geogent/commit/821bd635d3d842bca1ee55961c6bcbf01f08db25))


### Documentation

* retire CopilotKit references; document assistant-ui architecture ([06b8c4c](https://github.com/julianblue/geogent/commit/06b8c4cd42cbcf23f89a69acb6f663b1b09d8c79))

## [0.3.0](https://github.com/julianblue/geogent/compare/geogent-agent-v0.2.0...geogent-agent-v0.3.0) (2026-05-24)


### Features

* **agent,backend:** grow geo tool surface; route classic agent through model factory ([7d18716](https://github.com/julianblue/geogent/commit/7d18716dcd0e73f29d2d4aaa0a65f31906cb9ee6))
* **agent+ui:** agent-driven Sentinel-2 rendering with deck.gl band math ([06ebed0](https://github.com/julianblue/geogent/commit/06ebed0a8523758ad955e16f36d76789ea495b22))
* **agent+ui:** agent-driven Sentinel-2 rendering with deck.gl band math ([a5ed08a](https://github.com/julianblue/geogent/commit/a5ed08ae093be1079e81937e3844d52d8b7579a9))
* **agent:** add STAC search tools (Earth Search v1 default) ([c7f3a72](https://github.com/julianblue/geogent/commit/c7f3a7270cbfc20c67ba75a62cb70bab045a1723))
* **agent:** production Postgres checkpointer for LangGraph ([1723b98](https://github.com/julianblue/geogent/commit/1723b98954f248e831bb3b0bf513e0ff47e30e0f))
* **agent:** route AGENT_MODEL=openrouter:* through the OpenRouter gateway ([4bd3561](https://github.com/julianblue/geogent/commit/4bd35616982e5dfe07c3cfa3f0589e8a1b9c5395))
* **agent:** wire LangSmith observability with run tagging ([3b33971](https://github.com/julianblue/geogent/commit/3b33971ffe3ea0702389d8e2866b4ce7ac6ae657))
* **deploy:** add Railway deployment for the full stack ([f2c39e5](https://github.com/julianblue/geogent/commit/f2c39e56b2143da7a0895c7d9eae4c3845f13392))
* **ui,agent:** migrate the chat UI to assistant-ui + add LangGraph e2e tests ([fd304e8](https://github.com/julianblue/geogent/commit/fd304e82a849228ce2d4315f3fdfb088085ddd6a))


### Bug Fixes

* **agent,backend:** preserve Bedrock-only setups; reject bad geometry inputs ([f101977](https://github.com/julianblue/geogent/commit/f1019770fdfe9a70e675f0e4dddbe265f92840e7))
* **agent/evals:** push LangSmith feedback correctly; address PR review ([ef94ab9](https://github.com/julianblue/geogent/commit/ef94ab943045f1b9db1ac63fafca971c8e26fe4c))
* **agent+ui:** address Copilot review + CI formatters ([8341e09](https://github.com/julianblue/geogent/commit/8341e09f6eca3b12ea1a6daf2e8671dcb32f1e8a))
* **agent:** address Copilot review on PR [#11](https://github.com/julianblue/geogent/issues/11) ([b1aced7](https://github.com/julianblue/geogent/commit/b1aced7e208be73d6dce24c358d722043b19fc18))
* **agent:** broaden STAC search trim + tolerate stringified bbox/intersects ([36573cb](https://github.com/julianblue/geogent/commit/36573cb83738cfb4ae7d17181a2e4ab7415290ab))

## [0.2.0](https://github.com/julianblue/geogent/compare/geogent-agent-v0.1.0...geogent-agent-v0.2.0) (2026-05-12)


### Features

* **agent,backend:** grow geo tool surface; route classic agent through model factory ([7d18716](https://github.com/julianblue/geogent/commit/7d18716dcd0e73f29d2d4aaa0a65f31906cb9ee6))
* **agent:** add STAC search tools (Earth Search v1 default) ([c7f3a72](https://github.com/julianblue/geogent/commit/c7f3a7270cbfc20c67ba75a62cb70bab045a1723))
* **agent:** route AGENT_MODEL=openrouter:* through the OpenRouter gateway ([4bd3561](https://github.com/julianblue/geogent/commit/4bd35616982e5dfe07c3cfa3f0589e8a1b9c5395))


### Bug Fixes

* **agent,backend:** preserve Bedrock-only setups; reject bad geometry inputs ([f101977](https://github.com/julianblue/geogent/commit/f1019770fdfe9a70e675f0e4dddbe265f92840e7))
* **agent:** broaden STAC search trim + tolerate stringified bbox/intersects ([36573cb](https://github.com/julianblue/geogent/commit/36573cb83738cfb4ae7d17181a2e4ab7415290ab))
