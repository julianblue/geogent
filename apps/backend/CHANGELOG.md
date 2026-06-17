# Changelog

## [0.5.0](https://github.com/julianblue/geogent/compare/geogent-backend-v0.4.0...geogent-backend-v0.5.0) (2026-06-17)


### Features

* arbitrary AOI (geometry/bbox) + pixel-cap guard ([#65](https://github.com/julianblue/geogent/issues/65)) ([b5c3652](https://github.com/julianblue/geogent/commit/b5c3652f3ad4419ed78577d598b535a9a5e93bf3))
* **backend:** M1 artifacts registry + data-cube field-memory layer ([#65](https://github.com/julianblue/geogent/issues/65)) ([26436b6](https://github.com/julianblue/geogent/commit/26436b632d3fa8a45d42be2a2c9f278640300449))
* EuroCrops Germany (Brandenburg) parcels — ingest, crop queries, evals ([1d41e0c](https://github.com/julianblue/geogent/commit/1d41e0c7407abc3500b5884d4c3aba6287edd63c))
* extend index set + WarpedVRT-align zonal_stats ([#65](https://github.com/julianblue/geogent/issues/65)) ([1f51cf1](https://github.com/julianblue/geogent/commit/1f51cf1fb1181c9c7bd7ffffe49cc70d88506756))
* multi-collection cube (Sentinel-2 + Landsat) with reflectance scaling ([#65](https://github.com/julianblue/geogent/issues/65)) ([75ba17c](https://github.com/julianblue/geogent/commit/75ba17cd1169a6958f7cb24703856673617776e0))
* pluggable temporal reducer registry — composite/trend/frequency ([#65](https://github.com/julianblue/geogent/issues/65)) ([b4d2fd4](https://github.com/julianblue/geogent/commit/b4d2fd42f837717abc181dce832eba420bae96f6))
* **routing:** routing, isochrones & geocoding tools ([#55](https://github.com/julianblue/geogent/issues/55)) ([88fdd41](https://github.com/julianblue/geogent/commit/88fdd416b4c2c28d09e0bc94f709037edda59270))
* satellite data cubes — general temporal-raster engine + "field memory" zones ([#65](https://github.com/julianblue/geogent/issues/65)) ([973a9ab](https://github.com/julianblue/geogent/commit/973a9ab3c60e691c62460f84607968159f8a9587))
* **ui:** agriculture widgets — field selection, zonal stats, NDVI series, composite ([#24](https://github.com/julianblue/geogent/issues/24)) ([c00c9cc](https://github.com/julianblue/geogent/commit/c00c9cc2e7b0057ec721cad12ec6e2c2c5895198))
* **ui:** agriculture widgets — field selection, zonal stats, NDVI series, composite ([#24](https://github.com/julianblue/geogent/issues/24)) ([0428fbe](https://github.com/julianblue/geogent/commit/0428fbeac795b1ec6081a8b8022f6f12a9edb460))
* **ui:** render field-memory layers on the map ([#65](https://github.com/julianblue/geogent/issues/65)) ([85ea270](https://github.com/julianblue/geogent/commit/85ea270eebbee1ed01687c43f7eb61fffe3e8e93))


### Bug Fixes

* address PR [#69](https://github.com/julianblue/geogent/issues/69) review (owner dedup, asset allowlist, doc drift) ([#65](https://github.com/julianblue/geogent/issues/65)) ([e9299f3](https://github.com/julianblue/geogent/commit/e9299f3e19e024ae08aff97a11ac2ee96fef30cf))
* drop no-effect ellipsis bodies in ArtifactStore Protocol ([#65](https://github.com/julianblue/geogent/issues/65)) ([6c16e96](https://github.com/julianblue/geogent/commit/6c16e961d41f9d69a04fe3b5f87bdfc4dd56ee55))
* **routing:** address PR review — hardening & error clarity ([#55](https://github.com/julianblue/geogent/issues/55)) ([421bcd7](https://github.com/julianblue/geogent/commit/421bcd7272e0ec4b8449b52638a8938496672ecb))


### Documentation

* add repository CONTEXT.md and per-app CLAUDE.md guides ([f918d3e](https://github.com/julianblue/geogent/commit/f918d3e59e0df16ae0b6e5ec4a9643538da80841))

## [0.4.0](https://github.com/julianblue/geogent/compare/geogent-backend-v0.3.0...geogent-backend-v0.4.0) (2026-05-25)


### Features

* **backend:** add field/parcel model, ingestion, CRUD + bbox query ([30e20c7](https://github.com/julianblue/geogent/commit/30e20c71fe06d025abd1b6be8047697ce7f55220)), closes [#29](https://github.com/julianblue/geogent/issues/29)
* **backend:** agriculture raster compute — zonal stats + seasonal time-series ([fce034a](https://github.com/julianblue/geogent/commit/fce034a705d16eb493854ebb142b7e66e563f7ac))


### Bug Fixes

* add libexpat1 to Dockerfile apt-get install ([f1b15fb](https://github.com/julianblue/geogent/commit/f1b15fb26a4364021fbe09d3f0847b0cf579ab48))
* address PR review correctness feedback ([2e333dc](https://github.com/julianblue/geogent/commit/2e333dcab0aae18f1788c0338958877897dfb066))
* **backend:** validate STAC path segments to close partial SSRF ([e74fc2c](https://github.com/julianblue/geogent/commit/e74fc2cc511f740a3605f4c3035bf82d93c35f8a))

## [0.3.0](https://github.com/julianblue/geogent/compare/geogent-backend-v0.2.0...geogent-backend-v0.3.0) (2026-05-24)


### Features

* **agent,backend:** grow geo tool surface; route classic agent through model factory ([7d18716](https://github.com/julianblue/geogent/commit/7d18716dcd0e73f29d2d4aaa0a65f31906cb9ee6))
* **agent+ui:** agent-driven Sentinel-2 rendering with deck.gl band math ([06ebed0](https://github.com/julianblue/geogent/commit/06ebed0a8523758ad955e16f36d76789ea495b22))
* **agent+ui:** agent-driven Sentinel-2 rendering with deck.gl band math ([a5ed08a](https://github.com/julianblue/geogent/commit/a5ed08ae093be1079e81937e3844d52d8b7579a9))
* **agent:** production Postgres checkpointer for LangGraph ([1723b98](https://github.com/julianblue/geogent/commit/1723b98954f248e831bb3b0bf513e0ff47e30e0f))
* **deploy:** add Railway deployment for the full stack ([f2c39e5](https://github.com/julianblue/geogent/commit/f2c39e56b2143da7a0895c7d9eae4c3845f13392))
* **ui,backend:** JWT auth, login page, shadcn-driven copilot workspace ([c2a73d5](https://github.com/julianblue/geogent/commit/c2a73d540b6c654f392d20f071e74a0ac272423b))


### Bug Fixes

* **agent,backend:** preserve Bedrock-only setups; reject bad geometry inputs ([f101977](https://github.com/julianblue/geogent/commit/f1019770fdfe9a70e675f0e4dddbe265f92840e7))
* **backend,ci:** migration server_default SQL + gitleaks false positive ([5139ff0](https://github.com/julianblue/geogent/commit/5139ff03e1f198eb39089d3528ef1fbb914adb4b))
* **deploy:** address Railway PR review comments ([71d1a4b](https://github.com/julianblue/geogent/commit/71d1a4be063545958001d5824c82acc299b145d4))
* **ui,backend:** route group, type errors, redundant spatial index ([e245025](https://github.com/julianblue/geogent/commit/e245025d7ac8e837da7189f23373d234d305cc99))

## [0.2.0](https://github.com/julianblue/geogent/compare/geogent-backend-v0.1.0...geogent-backend-v0.2.0) (2026-05-12)


### Features

* **agent,backend:** grow geo tool surface; route classic agent through model factory ([7d18716](https://github.com/julianblue/geogent/commit/7d18716dcd0e73f29d2d4aaa0a65f31906cb9ee6))


### Bug Fixes

* **agent,backend:** preserve Bedrock-only setups; reject bad geometry inputs ([f101977](https://github.com/julianblue/geogent/commit/f1019770fdfe9a70e675f0e4dddbe265f92840e7))
