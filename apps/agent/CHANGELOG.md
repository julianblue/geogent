# Changelog

## [0.5.0](https://github.com/julianblue/geogent/compare/geogent-agent-v0.4.0...geogent-agent-v0.5.0) (2026-06-17)


### Features

* **agent:** conversation context trimming + eval guardrail scorer & coverage ([aba426c](https://github.com/julianblue/geogent/commit/aba426c9681da221063e4c8b5a5dbc27583e9526))
* **agent:** field-memory data tool + show_field_memory render tool ([#65](https://github.com/julianblue/geogent/issues/65)) ([2b0aa29](https://github.com/julianblue/geogent/commit/2b0aa293953ba1780d977ba2e928d4e048dcff0c))
* **agent:** optional dedicated summary model for the trimmer ([8b5f69e](https://github.com/julianblue/geogent/commit/8b5f69e4e61c45ec3a770e7740138c98d0680f58))
* **agent:** summarizing trimmer — fold dropped turns into a running summary ([7ae69ef](https://github.com/julianblue/geogent/commit/7ae69efefdab7b8e450aab9b0c44cd6e281c58ec))
* **agent:** tool-contract + prompt fixes clear both xfail eval cases ([3442be5](https://github.com/julianblue/geogent/commit/3442be5a39f3e2f0588e9c82c91eefe46a4f7cc7))
* arbitrary AOI (geometry/bbox) + pixel-cap guard ([#65](https://github.com/julianblue/geogent/issues/65)) ([b5c3652](https://github.com/julianblue/geogent/commit/b5c3652f3ad4419ed78577d598b535a9a5e93bf3))
* EuroCrops Germany (Brandenburg) parcels — ingest, crop queries, evals ([1d41e0c](https://github.com/julianblue/geogent/commit/1d41e0c7407abc3500b5884d4c3aba6287edd63c))
* extend index set + WarpedVRT-align zonal_stats ([#65](https://github.com/julianblue/geogent/issues/65)) ([1f51cf1](https://github.com/julianblue/geogent/commit/1f51cf1fb1181c9c7bd7ffffe49cc70d88506756))
* multi-collection cube (Sentinel-2 + Landsat) with reflectance scaling ([#65](https://github.com/julianblue/geogent/issues/65)) ([75ba17c](https://github.com/julianblue/geogent/commit/75ba17cd1169a6958f7cb24703856673617776e0))
* pluggable temporal reducer registry — composite/trend/frequency ([#65](https://github.com/julianblue/geogent/issues/65)) ([b4d2fd4](https://github.com/julianblue/geogent/commit/b4d2fd42f837717abc181dce832eba420bae96f6))
* **routing:** routing, isochrones & geocoding tools ([#55](https://github.com/julianblue/geogent/issues/55)) ([88fdd41](https://github.com/julianblue/geogent/commit/88fdd416b4c2c28d09e0bc94f709037edda59270))
* satellite data cubes — general temporal-raster engine + "field memory" zones ([#65](https://github.com/julianblue/geogent/issues/65)) ([973a9ab](https://github.com/julianblue/geogent/commit/973a9ab3c60e691c62460f84607968159f8a9587))
* **ui:** agent-composed dashboards via curated render_dashboard tool ([6d372b5](https://github.com/julianblue/geogent/commit/6d372b5c011b74f6ffd433e880df72b204d68f50))
* **ui:** agriculture widgets — field selection, zonal stats, NDVI series, composite ([#24](https://github.com/julianblue/geogent/issues/24)) ([c00c9cc](https://github.com/julianblue/geogent/commit/c00c9cc2e7b0057ec721cad12ec6e2c2c5895198))
* **ui:** agriculture widgets — field selection, zonal stats, NDVI series, composite ([#24](https://github.com/julianblue/geogent/issues/24)) ([0428fbe](https://github.com/julianblue/geogent/commit/0428fbeac795b1ec6081a8b8022f6f12a9edb460))
* **ui:** deck.gl analytics aggregation layers — heatmap & hexbin ([#57](https://github.com/julianblue/geogent/issues/57)) ([ef40d2f](https://github.com/julianblue/geogent/commit/ef40d2fb5dc391518848a80613391c07a9c6bf8d))


### Bug Fixes

* **agent:** budget only the unsummarized tail; bounded summarizer-failure fallback ([56cab0e](https://github.com/julianblue/geogent/commit/56cab0ef153670553417608f80d30b8e6205c2b0))
* **agent:** enforce min_length on DashboardSpec lists to match Zod ([57d68ad](https://github.com/julianblue/geogent/commit/57d68ada270672b36914e7f2f93185b36191da42))
* **agent:** smaller trim fallback + tools_forbidden parse tests ([46a5c7b](https://github.com/julianblue/geogent/commit/46a5c7b66419be4471665b86e37e41798380a911))
* **routing:** address PR review — hardening & error clarity ([#55](https://github.com/julianblue/geogent/issues/55)) ([421bcd7](https://github.com/julianblue/geogent/commit/421bcd7272e0ec4b8449b52638a8938496672ecb))


### Documentation

* add repository CONTEXT.md and per-app CLAUDE.md guides ([f918d3e](https://github.com/julianblue/geogent/commit/f918d3e59e0df16ae0b6e5ec4a9643538da80841))
* **adr:** recommend assistant-ui generative UI over json-render/A2UI ([c976d7f](https://github.com/julianblue/geogent/commit/c976d7f66df6884b5e0d1a37b248a6f57628d5f6))

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
