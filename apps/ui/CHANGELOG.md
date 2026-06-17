# Changelog

## [0.4.0](https://github.com/julianblue/geogent/compare/geogent-ui-v0.3.0...geogent-ui-v0.4.0) (2026-06-17)


### Features

* pluggable temporal reducer registry — composite/trend/frequency ([#65](https://github.com/julianblue/geogent/issues/65)) ([b4d2fd4](https://github.com/julianblue/geogent/commit/b4d2fd42f837717abc181dce832eba420bae96f6))
* **routing:** routing, isochrones & geocoding tools ([#55](https://github.com/julianblue/geogent/issues/55)) ([88fdd41](https://github.com/julianblue/geogent/commit/88fdd416b4c2c28d09e0bc94f709037edda59270))
* satellite data cubes — general temporal-raster engine + "field memory" zones ([#65](https://github.com/julianblue/geogent/issues/65)) ([973a9ab](https://github.com/julianblue/geogent/commit/973a9ab3c60e691c62460f84607968159f8a9587))
* **ui:** agent-composed dashboards via curated render_dashboard tool ([6d372b5](https://github.com/julianblue/geogent/commit/6d372b5c011b74f6ffd433e880df72b204d68f50))
* **ui:** agentic UI workspace — widgets, insights, layers, selection ([#16](https://github.com/julianblue/geogent/issues/16)–[#19](https://github.com/julianblue/geogent/issues/19)) ([02149b8](https://github.com/julianblue/geogent/commit/02149b881616918f80457b01af03d3f5921f728b))
* **ui:** agriculture widgets — field selection, zonal stats, NDVI series, composite ([#24](https://github.com/julianblue/geogent/issues/24)) ([c00c9cc](https://github.com/julianblue/geogent/commit/c00c9cc2e7b0057ec721cad12ec6e2c2c5895198))
* **ui:** agriculture widgets — field selection, zonal stats, NDVI series, composite ([#24](https://github.com/julianblue/geogent/issues/24)) ([0428fbe](https://github.com/julianblue/geogent/commit/0428fbeac795b1ec6081a8b8022f6f12a9edb460))
* **ui:** deck.gl analytics aggregation layers — heatmap & hexbin ([#57](https://github.com/julianblue/geogent/issues/57)) ([ef40d2f](https://github.com/julianblue/geogent/commit/ef40d2fb5dc391518848a80613391c07a9c6bf8d))
* **ui:** fail-closed owner check on thread mutations ([#20](https://github.com/julianblue/geogent/issues/20)) ([0beb433](https://github.com/julianblue/geogent/commit/0beb43350ed8516f0f9fcd0a5feb5d0efb7419e5))
* **ui:** insights workspace — drawer+rail layout + Recharts primitives ([#17](https://github.com/julianblue/geogent/issues/17)) ([93ba53f](https://github.com/julianblue/geogent/commit/93ba53fe2016db1f250bb3feebad89d2368f435e))
* **ui:** layer manager + card→map affordances + agent-action undo ([#18](https://github.com/julianblue/geogent/issues/18)) ([c4763d7](https://github.com/julianblue/geogent/commit/c4763d7b0cc70dd4b808208ddd1c2c2cfa207e30))
* **ui:** multi-conversation thread list + per-user scoping ([#20](https://github.com/julianblue/geogent/issues/20)) ([a908529](https://github.com/julianblue/geogent/commit/a908529b002381d3955b1507d110cb013f160484))
* **ui:** per-thread map/insights snapshots ([#20](https://github.com/julianblue/geogent/issues/20)) ([ada91ef](https://github.com/julianblue/geogent/commit/ada91ef04836882f840f2ea900399e2dc20846dd))
* **ui:** per-user authorization for LangGraph threads in /api/lg proxy ([377f5ba](https://github.com/julianblue/geogent/commit/377f5baaa5ae60652443e18123e72897204588f0))
* **ui:** render field-memory layers on the map ([#65](https://github.com/julianblue/geogent/issues/65)) ([85ea270](https://github.com/julianblue/geogent/commit/85ea270eebbee1ed01687c43f7eb61fffe3e8e93))
* **ui:** selection-as-context + generalized HITL approvals ([#19](https://github.com/julianblue/geogent/issues/19)) ([64db9c7](https://github.com/julianblue/geogent/commit/64db9c72ff5eca51afff3aff89280a1556258216))
* **ui:** sturdy chat foundation — issue [#14](https://github.com/julianblue/geogent/issues/14) ([c08b9d2](https://github.com/julianblue/geogent/commit/c08b9d2f90a94355ab9c8ccb176644a48c4afe5d))
* **ui:** widget framework for dual-mode tool widgets ([#16](https://github.com/julianblue/geogent/issues/16)) ([2897d3e](https://github.com/julianblue/geogent/commit/2897d3ea103b08649a484df19ac0a72287c59ba3))


### Bug Fixes

* **routing:** address PR review — hardening & error clarity ([#55](https://github.com/julianblue/geogent/issues/55)) ([421bcd7](https://github.com/julianblue/geogent/commit/421bcd7272e0ec4b8449b52638a8938496672ecb))
* **ui:** address Phase 2 review findings ([#18](https://github.com/julianblue/geogent/issues/18)/[#19](https://github.com/julianblue/geogent/issues/19)) ([b24647f](https://github.com/julianblue/geogent/commit/b24647f26fe230464cb382d7ce5edb27188f7846))
* **ui:** address review findings on widget framework ([#16](https://github.com/julianblue/geogent/issues/16)/[#17](https://github.com/julianblue/geogent/issues/17)) ([30e4453](https://github.com/julianblue/geogent/commit/30e445320947bfee01a4e9c86f6a3604c7a14b75))
* **ui:** drop unused useRef import in MapView (CodeQL) ([1e0f1e7](https://github.com/julianblue/geogent/commit/1e0f1e746f9d87844afb5a5b07019c2c3b566fd5))
* **ui:** fail closed in /api/lg ownership check on read errors ([2d8ad6e](https://github.com/julianblue/geogent/commit/2d8ad6e867c406bc5b3069f7609277c4b8165c31))
* **ui:** forward AbortSignal to field fetch; guard composite select value ([1c10d91](https://github.com/julianblue/geogent/commit/1c10d91e26f29124c5d74e199c5c8cec20494cbe))
* **ui:** harden auto-title; focus-visible thread menu ([#20](https://github.com/julianblue/geogent/issues/20)) ([229e950](https://github.com/julianblue/geogent/commit/229e950344487bfb8d29181bdec9f46782a482fc))
* **ui:** harden snapshot parsing and post-restore persist baseline ([#20](https://github.com/julianblue/geogent/issues/20)) ([5c4935e](https://github.com/julianblue/geogent/commit/5c4935e7ba8703ca844a168c3cbd196e20eec839))
* **ui:** parse string tool results so agriculture widgets actually render ([0c9638f](https://github.com/julianblue/geogent/commit/0c9638f3e9a9d22f3491acd1e6853be555f64ff4))

## [0.3.0](https://github.com/julianblue/geogent/compare/geogent-ui-v0.2.0...geogent-ui-v0.3.0) (2026-05-25)


### Features

* **ui:** adopt assistant-ui registry thread, markdown & streaming controls ([e6c8bf2](https://github.com/julianblue/geogent/commit/e6c8bf2578e41063591a350e01a63ff127f6345c)), closes [#14](https://github.com/julianblue/geogent/issues/14) [#15](https://github.com/julianblue/geogent/issues/15)


### Bug Fixes

* **ui:** address Copilot review on chat foundation ([6d9af62](https://github.com/julianblue/geogent/commit/6d9af62ebc02c25f503a5236b86687a650f57601))
* **ui:** prettier-format generated CHANGELOG to unblock CI ([45f46f5](https://github.com/julianblue/geogent/commit/45f46f5dc7590b483873306db7ced5cbe704769b))

## [0.2.0](https://github.com/julianblue/geogent/compare/geogent-ui-v0.1.0...geogent-ui-v0.2.0) (2026-05-24)

### Features

- **agent+ui:** agent-driven Sentinel-2 rendering with deck.gl band math ([06ebed0](https://github.com/julianblue/geogent/commit/06ebed0a8523758ad955e16f36d76789ea495b22))
- **agent+ui:** agent-driven Sentinel-2 rendering with deck.gl band math ([a5ed08a](https://github.com/julianblue/geogent/commit/a5ed08ae093be1079e81937e3844d52d8b7579a9))
- **deploy:** add Railway deployment for the full stack ([f2c39e5](https://github.com/julianblue/geogent/commit/f2c39e56b2143da7a0895c7d9eae4c3845f13392))
- **ui,agent:** migrate the chat UI to assistant-ui + add LangGraph e2e tests ([fd304e8](https://github.com/julianblue/geogent/commit/fd304e82a849228ce2d4315f3fdfb088085ddd6a))
- **ui,backend:** JWT auth, login page, shadcn-driven copilot workspace ([c2a73d5](https://github.com/julianblue/geogent/commit/c2a73d540b6c654f392d20f071e74a0ac272423b))

### Bug Fixes

- **agent+ui:** address Copilot review + CI formatters ([8341e09](https://github.com/julianblue/geogent/commit/8341e09f6eca3b12ea1a6daf2e8671dcb32f1e8a))
- **deploy:** address Railway PR review comments ([71d1a4b](https://github.com/julianblue/geogent/commit/71d1a4be063545958001d5824c82acc299b145d4))
- **ui,backend:** route group, type errors, redundant spatial index ([e245025](https://github.com/julianblue/geogent/commit/e245025d7ac8e837da7189f23373d234d305cc99))
