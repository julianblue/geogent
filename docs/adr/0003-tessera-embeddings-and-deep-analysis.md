# ADR 0003: TESSERA embeddings & deep-analysis architecture

Status: **proposed** · Date: 2026-10-18 · Branch: `feat/tessera-embeddings-spike`

Builds on: ADR 0002 (content-addressed artifacts; "the agent manipulates
_handles_, never pixels"), ADR 0001 (curated widgets / `render_dashboard`), and
the `#60` embeddings-similarity item under epic #27 (`CONTEXT.md` § Direction).

## TL;DR

Add **pixel-embedding analytics** on top of the TESSERA foundation-model
embeddings, and a **background "deep analysis" worker** for multi-step,
multi-year, regional questions. Two linked bets, one rule:

> **Capability before agent architecture.** The bottleneck for these use cases
> is backend data/compute, not the agent loop. Ship the embedding provider and
> field-level artifacts first; add deep-agent machinery only once fixed tools
> are shown to be the limit.

Chosen path, in phases (see "Phasing"):

1. **P0 — spikes (this branch):** prove read latency, field-embedding quality,
   and the license question (see "Spike results").
2. **P1 — provider + field-embedding artifact + PCA layer** on the EuroCrops
   fields we already have.
3. **P2 — similarity / clustering + a scatter widget.**
4. **P3 — field-source ingest (FTW), `classify_fields`, season regime.**
5. **P4 — playbooks** (on-demand recipe loading, keeps the system prompt lean).
6. **P5 — deep-analysis worker** (a `deepagents` agent behind the existing
   submit/poll job pattern; the interactive graph is **not** replaced).

Deliberately deferred: TiTiler, pgvector, sandboxed code execution, switching
the interactive agent to `deepagents`.

## Context

### The data: TESSERA v1.1 (University of Cambridge)

- **What:** global, **annual**, **128-d int8** embedding per **10 m** pixel,
  **2017–2025**, learned from a _full year_ of Sentinel-1 + Sentinel-2.
- **Where:** AWS Open Data, an **Icechunk (Zarr v3)** store at
  `s3://tessera-embeddings/v1.1/dclimate.icechunk` (us-west-2, anonymous
  access). Grouped by **UTM zone**; values are `int8` with a per-pixel
  `float32` scale (dequantise = `int8 × scale`). Chunks `256² × 128 × 1 yr`
  (~8.4 MB). ~**66 TiB** total — never mirrored, always windowed reads.
- **Annual only.** There is **no intra-annual embedding**. "Season detection"
  therefore means **season-_regime_ classification** (winter cereal / spring
  crop / summer crop / double crop / grassland) from the annual vector — not
  phenological timing. Timing and the _why_ come from pairing with the existing
  S2 index series (`seasonal_index_time_series_for_field`, `field_memory_for_field`).
- **License conflict (open question):** the data registry says **CC-BY-SA**, the
  repo says **CC0**. Unresolved; blocks any redistribution of derived products
  until settled (see Risks, Spike results).

### Field data (the "what to attach embeddings to")

- **FTW (Fields of the World):** harmonized national declarations as **fiboa
  GeoParquet** on Source Cooperative (**per-collection licenses**), plus FTW
  global **predicted boundaries** for 2024/2025 (CC-BY-4.0; "alpha" paths).
- **Already in the repo:** EuroCrops parcels in `models/field.py`
  (`crop`, `season`) loaded by `scripts/ingest_eurocrops.py` — i.e. **labelled
  training data** with no new ingest.

### What we can reuse

- **Artifacts registry** (`models/artifact.py`, `services/artifact_service.py`,
  `docs/design/m1-artifacts-data-model.md`): content-addressed (`recipe_hash`),
  lifecycle (`status`), payload out of the row, UNIQUE per `owner`.
- **Cube/reducer path** (`geo/cube.py`, `geo/reducers.py`): `write_single_band_cog`,
  the `REDUCERS` registry with named colormaps, `CubeError`.
- **Job pattern:** submit → poll → result (`api/v1/routes/raster.py`,
  `models/raster_job.py`; agent-side polling constants in `tools/geo_tools.py`).
- **UI:** `LayerSource` arm `fieldMemory` + `FieldMemoryOverlay.tsx` /
  `FieldMemoryLayerTool.tsx` paint single-band COGs via a colormap; the widget
  registry (`components/assistant/widgets/registry.ts`) and `render_dashboard`.
- **Dependency quarantine precedent:** heavy GDAL-stack deps live in the
  `ingest` group of `apps/backend/pyproject.toml`, outside CI's dev env.

### Use cases this unlocks

1. **Field dossier** — year-over-year embedding distance (rotation history),
   neighbour-label crop per year, intra-field heterogeneity → candidate zones,
   plus the NDVI curve for explanation.
2. **Season-regime map** — per-field / per-pixel regime class from the annual
   vector.
3. **Phenology archetypes** — cluster fields on embeddings, return **medoid**
   fields, feed their NDVI curves to the S2 series tool.
4. **Label transfer** — train on labelled EuroCrops/declarations, classify
   across years and borders onto FTW polygons.
5. **Declaration / boundary QA** — fields whose embedding disagrees with their
   declared crop or whose interior is bimodal.
6. **Similar-field search** (`#60`).

## Decisions

Marked recommended; this ADR is **proposed** pending owner sign-off.

### D1 — Capability before agent architecture ✅

Sequence work so each step ships user-visible value on the **existing**
interactive agent. The embedding provider, field artifacts, and derived layers
(D2–D5) come first; new tools (D6) are thin wrappers over them. Deep-agent
machinery (D7, D8) is gated behind demonstrated need. Rationale: every use case
above is limited by "can the backend read, reduce, and cluster embeddings
cheaply", not by how the agent plans.

### D2 — Embeddings are server-side artifacts; new provider `geo/tessera.py` ✅

Applies ADR 0002's rule: **the agent manipulates handles, never pixels.** A new
provider module `apps/backend/src/geogent_backend/geo/tessera.py`, following
the `geo/` provider convention (typed error class, explicit timeouts from
`config.py`, response normalization; mirror `stac.py`/`routing.py`):

- open the Icechunk store read-only/anonymous via `icechunk` + `xarray` (lazy);
- **UTM-zone selection** from the polygon; **polygon reprojection** into the
  zone CRS; window the read to the polygon bbox (chunk-aligned);
- **dequantise** (`int8 × scale`), **NaN/inf masking** (nodata, scale ≤ 0), and
  per-pixel **QC flags** (masked fraction, edge-of-zone);
- `TesseraError` mapped to **502** (upstream) / **503** (unconfigured) in the
  route, per `apps/backend/CLAUDE.md`.

New dependencies, **isolated**: `icechunk`, `xarray`, `zarr`,
`numcodecs[pcodec]`. ADR 0002 D2 rejected xarray for the _cube_ because the
field-scale cube is tiny; here the Zarr/Icechunk store **is** the data model
and has no numpy+rasterio equivalent, so the trigger ADR 0002 named ("→
xarray/Zarr") is met. Put them in a dedicated dependency group (mirroring
`ingest`), imported lazily inside `geo/tessera.py` so the default
`uv sync --all-groups` CI env and the no-DB/no-network test suite stay lean;
tests drive the provider with an in-memory Icechunk/Zarr fixture, no network.

### D3 — Field-level embedding artifact first; pgvector later ✅

The unit of analysis is the **field**, not the pixel: a per-field **mean** (and
**dispersion**) embedding keyed `(field_source, field_id, year)`, computed by
polygon-masked reduction and **cached** as a new `Artifact` kind (reuses
`recipe_hash` dedup, owner scoping, lifecycle). Payload is a **parquet/npz**
artifact in object storage; only a compact `summary` (n_fields, year, dim,
masked fraction) reaches the agent.

- _Deferred:_ **pgvector** — add only if **real-time similarity search across
  large sets** is needed (spike will size this). Brute-force cosine over
  tens of thousands of 128-d vectors in numpy is fine until then.
- Embedding **dimension is configurable**, not hard-coded to 128 (TESSERA v2
  is expected to ship Matryoshka dims; see Risks).

### D4 — Only derived rasters reach the UI ✅

No 128-band serving. The browser gets **single/triple-band** derived layers:

- **PCA(3) RGB** COG — needs a **3-band writer** next to
  `write_single_band_cog` in `geo/cube.py` (that function is deliberately
  single-band, one URL per layer);
- **similarity map** (cosine to a reference field/pixel set) — single-band;
- **cluster map** — single-band categorical.

Single-band outputs register in `REDUCERS`-style specs (`geo/reducers.py`) and
reuse the colormap names/GLSL ramps. UI: a new `LayerSource` arm
(`embedding`) validated in `parseLayers` and repainted per
`apps/ui/CLAUDE.md` § Per-thread snapshot. **TiTiler stays deferred** (as in
ADR 0002 D4): small field-scale rasters are read whole by deck.gl-geotiff.

### D5 — Field sources: GeoParquet via duckdb, clipped ingest into PostGIS ✅

FTW/fiboa collections are queried with **duckdb bbox pushdown** over GeoParquet
and **clipped to the AOI before ingest** into PostGIS, mirroring
`scripts/ingest_eurocrops.py` (a script / `ingest`-group dependency, not a
request-path dependency). Rules:

- **License is recorded per collection** at ingest (column or source table);
  **non-commercial (NC) collections are excluded by default** and require an
  explicit opt-in flag.
- Predicted-boundary "alpha" paths are treated as unstable: pin the path, store
  the snapshot date, tolerate schema drift.
- `fields` today has only `(name, crop, season, geometry)`; ingest adds
  `source` + `source_id` (+ `license`) via an Alembic revision
  (`make revision m=...`) so the `(field_source, field_id)` key in D3 is real.

### D6 — Agent tools: flat typed args, backend first, jobs for heavy work ✅

Per `apps/agent/CLAUDE.md`: backend endpoint first, then a thin tool via
`get_backend_client()`; register in `tools/__init__.py` **and** document in
`prompts/system.py`; module constants (not args) for poll cadence.

Data tools (return facts/handles, answer from these):

| Tool                      | Returns                                                         |
| ------------------------- | --------------------------------------------------------------- |
| `field_embedding_profile` | per-year distance, neighbour-label crop, heterogeneity, handle  |
| `embedding_layer`         | artifact handle + render URL, `kind` = `pca`/`similarity`/`clusters` |
| `find_similar_fields`     | ranked field ids + distances (`#60`)                            |
| `cluster_fields`          | cluster summary + **medoid field ids** to feed the S2 series tool |
| `classify_fields`         | per-field label + confidence, from labelled fields              |

Multi-year or regional calls are **jobs** (submit → poll → result, same shape as
`seasonal_index_time_series_for_field`).

UI-action tools (acks only, per the UI-vs-data invariant): `show_embedding_layer`
(paints the D4 layer) and `show_embedding_scatter` — a **new widget**: 2-D
projection (PCA/UMAP-precomputed server-side) of field embeddings, **linked to
map selection** (click point ↔ select field in `MapStateProvider`). Registered
via the widget registry; Zod schema mirrored from the Pydantic model (ADR 0001
sync caveat applies).

**Evals:** model new cases on `crops_grown_in_viewport` (single data tool,
`final_contains_any`) and `agriculture_field_ndvi_stats_and_series` (multi-tool
trajectory) in `apps/agent/tests/evals/cases/core.yaml`; recordings store
handles + summaries only (ADR 0002). Adding tools never breaks replay; renaming
existing ones does.

### D7 — Skills / playbooks: on-demand recipe loading ✅

`SYSTEM_PROMPT` already carries tool docs and the agriculture workflow
sequence for ~31 tools; every multi-step analysis (dossier, label transfer)
inlined there would bloat every turn. Instead, keep per-analysis **recipes** as
markdown playbooks loaded on demand:

- **Now:** a `load_playbook(name)` data tool (a flat enum arg, returns the
  recipe text; the prompt lists names + one-line triggers only).
- **Later:** `deepagents` `SkillsMiddleware` once the LangChain 1.x upgrade
  (D8) lands; the playbook files are written to be forward-compatible.

### D8 — Deep analysis = background job whose worker is a deep agent ✅

For questions like "profile rotation history for every winter-cereal field in
this county 2018–2025 and cluster them", the work is long, multi-step, and
produces a report — a poor fit for the synchronous chat loop.

- **Worker:** a [`deepagents`](https://github.com/langchain-ai/deepagents) 0.7.x
  agent (todo planning, virtual FS, subagents, skills). It requires
  **`langchain>=1.4.6`**; `apps/agent/pyproject.toml` pins `langchain>=0.3.7`
  today, so a **LangChain 1.x upgrade is a prerequisite** (own PR, own eval
  run).
- **Worker tool set: data tools only** (D6 data tools, S2 series, field/crop
  queries). No frontend-action tools, no `interrupt()`.
- **Output:** a **report artifact** (markdown + embedded dashboard specs) plus
  **layer handles** (D4), stored as `Artifact`s.
- **Main agent surface:** `start_deep_analysis` / `show_analysis_report`
  exposed through the existing **submit/poll job pattern** — the interactive
  graph just starts and polls; it never hosts the deep loop.
- **The interactive `graphs/geo_analyst.py` ReAct loop is NOT replaced.**
  Reasons: (a) **frontend-action tools and `interrupt()` HITL must stay
  top-level** — subagent tool calls stream in a separate namespace and
  interrupt propagation out of subagents is undocumented (CONTEXT.md principle
  #3 is non-negotiable); (b) eval replay recordings key on **tool names** and
  trajectories, so swapping the loop invalidates the committed baseline;
  (c) `agent_node` context control (bounded history, `messages` never pruned)
  is built around the current graph.

### D9 — Fixed tools over code execution (for now) ✅

Expose analyses as typed tools, not a Python sandbox. A **sandboxed code-exec
backend** is admitted **only for the D8 worker**, and **only when fixed tools
demonstrably cannot express a needed analysis** (tracked as eval cases that fail
for that reason). If built: per-user isolation and **fail-closed** (CONTEXT.md
principle #5), no network, no provider keys, bounded CPU/memory/time, artifact
I/O by handle only.

## Alternatives considered

| Option                                        | Verdict                                                                                                                                             |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Switch the whole agent to `deepagents`        | **Rejected** — breaks top-level `interrupt()`/frontend-action invariants and eval replay (D8). Used as a worker only.                              |
| 128-band COG + client-side compute            | **Rejected** — ~40× the payload of a 3-band layer, and violates "agent/UI manipulate handles, not pixels"; also repeats work per viewer.  |
| TiTiler now                                   | **Deferred** — same reasoning as ADR 0002 D4; revisit when layers exceed field scale.                                                              |
| `geotessera` library as the data layer        | **Consider, not default.** Convenient, but pulls heavy deps (`geopandas`, `obstore`, `aiohttp`) and its NPY tile path is deprecated; direct `icechunk` + `xarray` (D2) is preferred. Re-evaluate if the Icechunk path proves fragile. |
| pgvector from day one                         | **Deferred** (D3) — adds an extension + index lifecycle before we know the search scale.                                                           |
| Inline all recipes in `SYSTEM_PROMPT`         | **Rejected** (D7) — token and tool-selection cost on every turn.                                                                                   |

## What it means for each app

**Backend** — `geo/tessera.py` (D2); new `Artifact` kinds
(`field_embeddings`, `embedding_layer`, `analysis_report`) and a 3-band writer
in `geo/cube.py` (D3/D4); a `services/embedding_service.py` for reduction,
PCA, similarity, clustering, and classification (numpy/scikit-learn-class deps
decided by spike); an auth-gated `routes/embeddings.py` registered in
`api/v1/router.py` (**router-level `get_current_user` dependency**, mirror
`routes/routing.py` — a missing gate is a security bug); `config.py` +
`.env.example` entries (store URI, region, timeouts, max-AOI / max-fields
caps, pixel-cap guard like the existing AOI guard in `artifact_service.py`);
Alembic revision for field `source`/`license` columns (D5). Tests: provider via
in-memory Zarr fixture; routes with the service monkeypatched; an auth-boundary
test.

**Agent** — D6 tools in a new `tools/embedding_tools.py` (data) and
`tools/frontend_actions.py` (UI acks); `load_playbook` (D7); later
`start_deep_analysis`/`show_analysis_report` (D8) plus a `deepagents` worker
module that is **not** wired into `graphs/geo_analyst.py`. Prompt additions
extend the "Agriculture workflow sequence": dossier recipe, and the rule
_"embedding results are never explained from the embedding alone — pair with
an index curve or labelled neighbours."_

**UI** — new `LayerSource` arm + overlay (D4), `show_embedding_layer` client
tool under `components/assistant/tools/`, `EmbeddingScatterWidget` registered in
`widgets/registry.ts` (Recharts or deck.gl scatter; selection linked through
`MapStateProvider`), analysis-report widget (P5), all under the snapshot
fail-closed rules in `apps/ui/CLAUDE.md`. Add a per-endpoint
`app/api/proxy/...` route for any new backend call.

## Phasing

| Phase | Scope                                                                                         | Exit criterion                                            |
| ----- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| P0    | Spikes on this branch: read latency, field-embedding sanity, license check, scale sizing      | "Spike results" filled; D2/D3 numbers confirmed or revised |
| P1    | `geo/tessera.py`, field-embedding artifact, PCA(3) RGB layer on EuroCrops fields              | PCA layer renders for a Brandenburg viewport              |
| P2    | `find_similar_fields`, `cluster_fields`, similarity/cluster layers, scatter widget            | Medoid → S2 NDVI curve flow works end to end              |
| P3    | FTW ingest (D5), `classify_fields`, season-regime map                                          | Cross-year/-border label transfer meets spike accuracy bar |
| P4    | `load_playbook` + first playbooks (dossier, label transfer, archetypes)                       | `SYSTEM_PROMPT` size flat while tool count grows          |
| P5    | LangChain 1.x upgrade, `deepagents` worker, `start_deep_analysis`/`show_analysis_report`      | One regional report produced from data tools only         |

## Risks & open questions

- **Cold latency from us-west-2.** First read of a zone/chunk set over the
  public internet may dominate request time. Mitigate: async jobs for >1 field,
  artifact cache (D3), chunk-aligned windows. Numbers: `TBD (spike)`.
- **UTM zone seams.** Fields straddling a zone boundary have no single-zone
  window; need per-zone reads + merge, or documented exclusion. `TBD (spike)`
  on how common this is for target regions.
- **FTW "alpha" paths** can move or change schema; pin and snapshot (D5).
- **"Year" window is undefined.** The annual embedding's temporal window is not
  calendar-aligned for all hemispheres/crops (southern hemisphere, winter
  crops spanning New Year). Must be confirmed from the TESSERA docs/spike
  before season-regime claims are made; surface the assumed window in every
  artifact `summary`.
- **v2 Matryoshka dims.** Make the embedding dimension a configurable,
  recorded-in-`recipe` parameter (D3) so truncated/larger variants don't
  invalidate the cache or schema.
- **Interpretability.** An embedding distance is not an explanation. Always pair
  with S2 index curves or labelled neighbours (prompt rule, D6).
- **License (CC-BY-SA vs CC0).** If SA applies, derived rasters/exports may need
  share-alike and attribution; resolve with upstream before shipping any export
  or public layer. Until resolved: private, per-user artifacts only.
- **FTW per-collection licenses** (some NC): enforced by D5 default-exclude;
  verify license propagates to anything we display or export.
- **Cost/abuse.** Region-scale embedding jobs are expensive; enforce AOI /
  field-count caps and per-user job quotas in config.
- **LangChain 1.x upgrade** is a cross-cutting change (agent graph, evals) and
  is on the critical path for P5 only — keep it out of P1–P4.

## Consequences

- A new heavyweight dependency tier (`icechunk`, `xarray`, `zarr`,
  `numcodecs[pcodec]`), quarantined behind `geo/tessera.py` and a dependency
  group; CI env stays lean.
- A new cloud read dependency (public S3, us-west-2) with no SLA; provider
  failures surface as 502 and are cacheable.
- The agent gains embedding tools but stays thin: all math is server-side and
  every output is a handle + summary + render URL.
- Evals grow a new class: **numeric correctness** against synthetic
  embeddings (planted clusters → expected medoids/labels) in addition to
  trajectory scoring; recordings never contain vectors.
- The Pydantic ↔ Zod schema-sync burden (ADR 0001) grows with the new
  `LayerSource` arm and scatter widget.
- The deep-analysis worker is additive and optional: if P0–P4 prove enough, P5
  can be dropped without rework.

## Spike results

> **TODO (orchestrator):** fill from the parallel P0 spikes. Keep to measured
> facts; every `TBD (spike)` elsewhere in this ADR should resolve here or be
> struck.

| Question                                                         | Result            |
| ---------------------------------------------------------------- | ----------------- |
| Cold read latency, single field (~10 ha), us-west-2 → backend    | TBD (spike)       |
| Warm read latency / bytes transferred per field                  | TBD (spike)       |
| Throughput: fields/min for a county-scale job (N workers)        | TBD (spike)       |
| Peak memory for a 1,000-field reduction                          | TBD (spike)       |
| Effective "year" window (calendar vs. other) per TESSERA docs    | TBD (spike)       |
| Fraction of target-region fields straddling UTM zone seams       | TBD (spike)       |
| Label-transfer accuracy: EuroCrops-trained, held-out year        | TBD (spike)       |
| Label-transfer accuracy: cross-border (e.g. DE → PL/CZ) FTW      | TBD (spike)       |
| Season-regime separability (silhouette / kNN purity)             | TBD (spike)       |
| Brute-force cosine search latency @ 10k / 100k / 1M fields      | TBD (spike)       |
| pgvector needed? (threshold from the row above)                  | TBD (spike)       |
| PCA(3) layer render check on a Brandenburg viewport              | TBD (spike)       |
| License: CC-BY-SA vs CC0 — upstream answer / link                | TBD (spike)       |
| `geotessera` vs direct `icechunk`+`xarray`: dep weight, fragility | TBD (spike)       |

## References

- Prior art: ADR 0001, ADR 0002, `docs/design/m1-artifacts-data-model.md`,
  `apps/backend/spikes/cube_zones/DECISION.md`,
  `apps/backend/spikes/raster_compute/DECISION.md`.
- Roadmap: epic #27; `#60` (embeddings similarity), `#56` (imagery
  intelligence); `docs/roadmap/satellite-data-cubes.md`.
- TESSERA (Univ. of Cambridge) v1.1 — store
  `s3://tessera-embeddings/v1.1/dclimate.icechunk` (AWS Open Data).
- Icechunk — <https://icechunk.io/> · Zarr v3 — <https://zarr.dev/> ·
  xarray — <https://docs.xarray.dev/>
- Fields of the World (FTW) / fiboa — <https://fiboa.org/> (Source Cooperative
  hosting; per-collection licenses).
- LangChain `deepagents` — <https://github.com/langchain-ai/deepagents>
