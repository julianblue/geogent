# Demo report — TESSERA field embeddings (PR #71, `feat/tessera-p1` @ `bd2b178`)

Date: 2026-10-18 · Model: `openrouter:anthropic/claude-sonnet-4.5` · Nothing committed to `feat/tessera-p1`.

## TL;DR

- **Backend + data path: solid.** Anonymous Icechunk reads through the proxy CA work. Latency beat the caveat estimates: 5-yr profile 2.6–5.6 s cold, PCA layer 7.3 s cold. Recipe caching works (0.0 s on a hit).
- **The signal is real.** Ground truth (Austrian declared crops 2019–2025) plus a green-fallow negative control show centred YoY distance **0.12–0.24 on a stable parcel vs 0.86–1.46 on rotating parcels**. Centring adds separation over raw (0.08–0.22 vs 0.24–0.39).
- **Two blocking UI bugs.** (B1) `show_embedding_layer` crashes the whole app at render and bricks the thread on reopen; that one is new in #71. (B2) Every server-tool widget disappears about 7 s after the run, and 3 extra LLM runs fire per turn; that one is a pre-existing bridge bug that #71 inherits.
- **The agent's verdict is unreliable.** It reported a crop rotation on the never-rotated control field (B3). It built a "winter crop throughout" story from NDVI that covered 2020 only, when the declared sequence was durum → vegetables → durum → soy → durum → vegetables (B5). It also asks for `end_year=2026` and gets a 422 in 3/3 runs (B4).
- With B1 patched locally (`fix-embedding-layer-render-crash.patch`), chats (b) and (c) work end to end. The PCA overlay renders correctly, and the layer plus viewport restore from the thread snapshot.

## Setup (and deviations from the handoff)

| Item | What I did |
|---|---|
| Stack | Docker daemon started manually; **only PostGIS in Docker** (`postgis/postgis:16-3.4`). Backend/agent/UI native (`uv sync --all-groups`, `pnpm install`): avoids proxy-CA plumbing inside image builds. |
| Agent port | **2124**, not 2024. 2024/2025 are bound by sandbox infra here; `LANGGRAPH_URL=http://localhost:2124` in `apps/ui/.env.local`. Environment-specific, not a repo bug. |
| LLM | `OPENROUTER_API_KEY` present. One-shot check returned `'ok'` in 1.9 s. |
| User | `demo@example.com`, used both as the UI login and as the agent's `BACKEND_SERVICE_EMAIL`, per the artifact-identity caveat. I did not hit the 404 caveat. |
| TLS | `SSL_CERT_FILE`/`AWS_CA_BUNDLE` were already set; icechunk honoured them. No verification disabled. |
| Fields | Real 2024 AT declared parcels from `ftw/harmonized-field-data` (DuckDB with bbox pruning, 246 parcels in the Marchfeld bbox), inserted via `POST /api/v1/fields`. |

| id | Name | 2024 crop | Area |
|---|---|---|---|
| 1 | Marchfeld A — AT parcel 112315774 | durum wheat | 10.27 ha |
| 2 | Marchfeld B — AT parcel 111930452 | grain maize | 9.06 ha |
| 3 | Marchfeld C — AT parcel 114752755 | sugar beet | 8.79 ha |
| 4 | Marchfeld D — green fallow control | GRÜNBRACHE every year 2020–2024 (≥0.99 overlap) | 2.55 ha |

## Chats run

| Chat | Tool calls chosen by the agent | Wall time | Result |
|---|---|---|---|
| (a) field 1 "changed year to year since 2020? rotate?" | `field_embedding_profile(1,2020,2026)` **→422** ‖ `seasonal_index_time_series_for_field(1, 2020-01-01..2026-12-31, ndvi)`; then `field_embedding_profile(1,2020,2025)` | 52.6 s to idle; 4 `runs/stream` | Dashboard + NDVI widget rendered, **then vanished** (B2). Answer: "rotated multiple times; winter crop throughout" (half wrong, B5). |
| (a) field 3 | same pattern, 422 retry again | dashboard at 34 s, run end 49 s, **dashboard gone at 56 s** | Answer: rotated (correct). Says 2020 NDVI is "consistent with sugar beet"; in 2020 the field was potatoes. |
| (a) field 4 (control) | same pattern, 422 retry again | dashboard 33 s, end 42 s | **False positive:** "Yes, the crop likely rotated… 2022→2023 (0.238) strongly suggesting a crop rotation" (B3). |
| (b) field 1 PCA 2024 | `embedding_layer(2024, field_id=1)` → `show_embedding_layer(artifact_id, label)` | 8.2 s | **App crash** (B1). The thread re-crashes on every reopen. |
| (b) again, B1 patched locally | same two calls | 18.4 s | Layer registered and legend shown, but the map stayed on San Francisco (B11). A follow-up "zoom to field 1" made the agent call `fly_to` (8.6 s). The overlay renders correctly (UTM 33N → WebMercator, strip parcels crisp). |
| (c) reload → other thread → reopen | — | — | ✅ Layer, opacity, legend and viewport restored from `metadata.snapshot`. The other thread correctly reset to its own state. |

The agent did pair the profile with `seasonal_index_time_series_for_field` every time, as the prompt instructs. It never used `list_fields`; it referenced fields by id directly.

### Latencies (backend direct, cold unless noted)

| Call | Latency |
|---|---|
| `embedding-layers` field 1 / 2024 (88×113 px, EPSG:32633) | 7.3 s |
| `field-embeddings` 2020–2024: field 1 / 2 / 3 / 4 | 5.1 / 5.6 / 3.6 / 2.6 s |
| Same recipe again (cache hit) | 0.0 s |
| `GET /api/proxy/analytics/artifacts/{id}` from the browser | 3.1 s and 9.8 s (slow; it ran concurrently with an NDVI job) |
| `pca_rgb.tif` COG fetch via proxy | 1.8 s |

## Ground truth vs embedding signal

Declared crops come from `ftw/harmonized-field-data/at/year=YYYY` (largest-overlap parcel per year). The four YoY values are the centred cosine distances for 2020→21, 21→22, 22→23 and 23→24.

| Field | 2020 → 2024 declared sequence | Centred YoY | Raw YoY |
|---|---|---|---|
| 1 | durum → field veg → durum → soy → durum | 1.08, 1.46, 1.06, 1.15 | 0.28, 0.38, 0.33, 0.37 |
| 2 | maize → field veg → veg (processing) → wheat → maize | 1.23, 1.08, 1.35, 0.98 | 0.30, 0.27, 0.35, 0.25 |
| 3 | potatoes → wheat → field veg → durum → sugar beet | 1.27, 0.86, 1.31, 1.12 | 0.36, 0.24, 0.33, 0.39 |
| 4 | fallow ×5 | **0.12, 0.17, 0.24, 0.12** | 0.13, 0.17, 0.22, 0.08 |

What this shows:

- **The profile discriminates well.** Every real crop change scored ≥0.86 centred, and the no-change parcel scored ≤0.24. In this sample, a fixed threshold around 0.5 would have classified all 16 pairs correctly.
- **Field 2's 2021→22 pair** (single-culture veg → processing veg) is the only "same-ish crop" pair. It scored 1.08, so the profile can't separate similar crop classes, which is expected at this granularity.
- **Small sample:** 4 parcels, one region. Treat ~0.5 as a hypothesis to validate on a larger labelled draw. This data source makes that cheap: thousands of parcels × 7 years.

## Bugs

### B1 — `show_embedding_layer` render crashes the app; thread bricked (HIGH, new in #71)

- **Repro:** chat "Show me an embedding false-colour view of field 1 for 2024." The run completes, then the Next.js overlay shows `TypeError: Cannot read properties of undefined (reading 'toUpperCase')` at `EmbeddingLayerTool.tsx:92`, and the whole React tree unmounts. Reload and click the thread: it crashes again every time. Screenshots `02a`, `02b`, `02d`.
- **Root cause:** `@assistant-ui/react-langgraph` maps a tool message to `result: message.content`, which is the server `ToolMessage` JSON **string** (`convertLangChainMessages.js:233`). So `result.mode` is `undefined`. The render typed `result` as the client `execute` return value.
- **Fix:** parse with the existing `parseToolResult` and default the mode. See `fix-embedding-layer-render-crash.patch` (3 lines; passes tsc, eslint and prettier). I applied it locally for the rest of the demo, then reverted the working tree.
- **Same latent bug, pre-existing:** `FieldMemoryLayerTool` renders `{result.band}` and survives only because `.band` isn't dereferenced further; it shows "undefined layer drawn on the map." Worth a test that renders each client tool with a string `result`.

### B2 — Frontend `execute` results re-submitted after the run: widgets vanish, extra LLM runs (HIGH, pre-existing bridge bug that #71 inherits)

- **Repro:** chat (a) on any field. The dashboard is visible at about 34 s and the run ends at about 49 s. At about 56 s the dashboard, the NDVI chart and the 422 error chip **all disappear**, and they stay gone after reload (`01a` vs `01b-*`/`01d`; `08a` vs `08b`).
- **Evidence:** the thread state ends with `ToolMessage(content="{}")` for **each** tool_call_id that was already answered, including the failed one, each followed by an empty AI message:

  ```
  7 tool field_embedding_profile toolu_…GpkSpGa '{}'
  9 tool seasonal_index_time_series_for_field toolu_…J4Z '{}'
  11 tool field_embedding_profile toolu_…YBup '{}'
  ```

  The UI log shows **4 `runs/stream` POSTs for one user turn**. Rendering reads the latest result for the id, which is `{}`, so `profileToDashboard(undefined)` returns null and the widget disappears.
- **Scope:** it also hits `seasonal_index_time_series_for_field` (main) and `fly_to` (Pattern A, main; thread `c121dde4` msgs 10–11). It did *not* hit `show_embedding_layer`, possibly because its async `execute` resolves after the server result lands. Pattern C (`execute: async () => ({})`) is the clearest trigger.
- **Cost:** 3 wasted LLM calls per analytics turn, and lost widgets in every saved thread.
- **Fix direction:** server-executed tools should register a **render-only** tool UI with no `execute`, so nothing is submitted. Alternatively, the runtime adapter should drop client results for tool_call_ids that already have a `ToolMessage`. Needs a look at the assistant-ui version's API; I didn't patch this.

### B3 — Agent reports rotation on a never-rotated parcel (MEDIUM–HIGH, prompt/contract)

- **Repro:** field 4 (fallow 2020–24). Centred YoY 0.12–0.24. The agent answered "Yes, the crop likely rotated… 2022→2023 (0.238) strongly suggesting a crop rotation." Transcript `transcripts/field4-control-rotation.txt`, screenshot `08c`.
- **Cause:** the `field_embedding_profile` docstring says distances "are relative: compare years within the field rather than against a fixed cut-off". With no absolute anchor, the maximum always looks like "the rotation".
- **Fix options, cheapest first:**
  1. Docstring: "if every centred distance is below ~0.5, report no rotation".
  2. Return a reference in `summary`, such as the AOI pixels' YoY distance distribution and the field's percentile, so "large" is defined per year and region.
  3. Calibrate on labelled AT/EuroCrops parcels and ship a threshold with the recipe version.

### B4 — `end_year` beyond the store range → 422 → retry, every run (MEDIUM)

- 3/3 runs asked for `end_year=2026` (the model reads "since 2020" as "through today"), got a 422 ("outside the TESSERA range 2017-2025"), then retried. That costs one LLM round trip, ~5–10 s, and leaves a red error chip in the transcript (until B2 wipes it).
- **Fix:** put the valid range in the docstring/prompt (render it from `TESSERA_MIN/MAX_YEAR`), or clamp server-side and report `clamped_to` in the summary.

### B5 — NDVI pairing covers only 2020, and the agent generalises from it (MEDIUM; the limit is pre-existing, #71 makes it load-bearing)

- `seasonal_index_time_series_for_field(2020-01-01..2026-12-31)` hits `max_scenes=60`, so all points fall in **Jan–Oct 2020**. The agent then wrote "consistent low summer NDVI across the time series… winter crop throughout 2020–2025" for field 1, against a truth of durum/veg/durum/soy/durum/veg. Field 3's run did admit "only 2020 data in detail" but still inferred sugar beet; 2020 was potatoes.
- The new prompt rule "pair with seasonal_index… for the same years" makes this tool the explanation layer, so its truncation now produces confident wrong narratives.
- **Fix:** per-year sampling (N scenes per year), monthly or annual composites, or have the agent call it per year. At minimum, return `truncated: true` plus the covered date range and tell the agent to state it.

### B6 — Dashboard stat tiles wrap per character in the chat panel (LOW, UI)

- Inline dashboard at ~400 px chat width: "MEA / N / YOY / CHA / NGE", and the value `1.19…` is clipped (`01a`, `08a`). The expanded view is fine (`08c`). The tiles need `min-width`, a responsive single-column layout, or fewer tiles inline.

### B7 — YoY chart visually overstates small changes (LOW, UI)

- The y-axis auto-scales: the control's 0.24 peak looks as dramatic as a real rotation (`08c`). The curve is monotone-smoothed between discrete year pairs. Two series (centred and raw) are drawn with **no legend**.
- **Suggest:** a fixed domain (e.g. 0–1.5), points or bars per pair, a legend, and optionally a reference band at the no-change level.
- The per-year table's "Heterogeneity" and "Usable" columns run together ("0.043 Yes").

### B8 — `apps/backend/.env.example` `CORS_ORIGINS` doesn't parse (LOW, pre-existing since `c2a73d5`)

- **Repro:** `cp .env.example .env && uv run alembic upgrade head` fails with `SettingsError: error parsing value for field "cors_origins" from source "DotEnvSettingsSource"`. `list[str]` from dotenv must be JSON.
- **Fix:** `CORS_ORIGINS=["http://localhost:3000"]` in the example, or a `NoDecode` + split validator.

### Smaller notes

- **B9 (UX):** `show_embedding_layer` draws wherever the viewport is. The agent doesn't fly there, so the first view shows nothing (`04b`). Suggest fit-to-bounds on add (the summary has `bbox_wgs84`) or a prompt rule to `fly_to` first.
- **B10:** the `field_embeddings` summary has `grid.width/height: null`. It's harmless, but drop the keys or fill them.
- **B11:** the sidebar keeps showing "New conversation" for the active thread after auto-titling, until reload (`04b`). Probably pre-existing.
- **B12:** `seed_user` rejects `*.local` emails (email-validator special-use domains). Trivial; noted only because the handoff suggested a non-example address.
- **Console:** after the B1 crash there is a React "Cannot update a component while rendering a different component … EmbeddingLayer" warning. I didn't see it independently of the crash.

## Caveats from the handoff, checked

| Caveat | Outcome |
|---|---|
| Artifact identity | Not hit (same account used). |
| Latency | Better than expected for profiles (2.6–5.6 s vs 15–20 s); layer ≈ as expected. |
| `epsg.io` | Reachable; the COG reprojected fine. |
| Calendar years | Visible in practice: the agent repeated the caveat, but the NDVI story ignored winter-crop straddling anyway. |
| License | Screenshots contain derived PCA imagery, so they are **not committed**; the `*.png` files below exist only in the demo session's local `demo/`. |

## Files

| Path | Contents |
|---|---|
| `00`–`01*` | chat (a) field 1, including widget loss after reload/reopen |
| `02*` | chat (b) crash, including the crash on reopen |
| `03*`–`05a` | patched (b), layer manager, zoomed overlay |
| `06a`–`06c` | (c) reload → other thread → restored |
| `07*`, `08*` | field 3 / field 4 control dashboards (inline, expanded, after wipe) |
| `transcripts/*.txt` | full tool-call transcripts per thread |
| `transcripts/truth.json` | declared crops 2019–2025 |
| `transcripts/profiles_2020_2024.json` | raw profile summaries |
| `fix-embedding-layer-render-crash.patch` | B1 fix |
| `console.log` | browser console warnings and errors |
