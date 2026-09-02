# apps/agent — CLAUDE.md

LangGraph ReAct agent: the **agricultural raster analyst**. Owns the system
prompt and the tool set; calls the backend for data and emits UI actions for the
browser. The tool surface is deliberately narrow — imagery, fields, and the
analytics over them — so tool selection stays sharp; general-purpose routing /
isochrone tools were removed (their backend endpoints remain).

> Big picture: `../../CONTEXT.md`. CI gate commands: root `../../CLAUDE.md`
> (`ruff format --check` is a separate gate from `ruff check`; `mypy` advisory;
> `pytest`). Eval harness: `tests/evals/README.md`.

Stack: LangChain + LangGraph (LangGraph Platform layout) · Python 3.12 · uv ·
models via OpenRouter through `models/` (`model_factory`).

## Graph

`graphs/geo_analyst.py` — a ReAct loop over `state.GraphState`:
`agent ↔ ToolNode`, looping until the model stops calling tools. Tool
exceptions are formatted back to the LLM as `tool` messages
(`handle_tool_errors=_format_tool_error`) so it can **retry with a fixed
payload** instead of crashing the run. `nodes/agent_node.py` binds `TOOLS` and
the system prompt to the model.

**Context control (`utils/context.py`).** Before each model call, `agent_node`
bounds history to `AGENT_MAX_HISTORY_TOKENS` (deterministic ~4-chars/token
trim, anchored on a human turn so tool-call pairs stay intact). With
`AGENT_HISTORY_SUMMARIZE` on (default), dropped turns are folded into a running
`summary` in `GraphState` (incremental — only newly-dropped turns are
summarized, via one extra model call) rather than discarded. **`messages` is
never pruned** — the UI renders the transcript from it — so trimming only shapes
what the model receives. Keep this property if you touch the node or state.

## Tools (`tools/`) — the core of the app

The `TOOLS` list in `tools/__init__.py` is the registry. Two families:

1. **Backend-data tools** — thin async wrappers that call the auth-gated backend
   via `get_backend_client()` and **return data to the model** (`geo_tools.py` →
   `/analytics/*`, `/fields/*`). `backend_client` logs in as a service user and
   caches the JWT (auto-refresh once on a 401) — **the agent never holds provider
   URLs or keys.**

   The four raster tools sit at four deliberately different altitudes, and the
   prompt teaches the model to pick between them: `zonal_stats_for_field` (one
   field, one date) → `seasonal_index_time_series_for_field` (raw per-scene
   series) → `analyze_index_season` (phenology metrics + anomaly vs previous
   years) → `temporal_features` (per-pixel reduction over a cube). Adding a
   fifth without a clear altitude of its own is how this surface goes blurry.
2. **Frontend-action tools** (`frontend_actions.py`) — either **client tools**
   (return an ack only; the browser executes + renders, e.g. `fly_to`,
   `add_buffer_layer`, `add_aggregation_layer`, `show_temporal_layer`) or
   **LangGraph `interrupt()` tools** for HITL (`confirm_feature_save`,
   `show_sentinel2_scene`) that pause until the UI resumes the graph.

The **direct external calls** (no backend proxy, by design) are
`osm_tools.geocode_place` (Nominatim) and `stac_tools.py` (STAC / Earth Search) —
kept direct so committed eval recordings stay stable.

### Invariants when adding/changing tools

- **New data capability → backend first**, then a thin tool calling it via
  `get_backend_client()`. Never put URLs/keys in the agent.
- **Register in `tools/__init__.py` AND document in `prompts/system.py`.** The
  prompt is load-bearing: it encodes the **UI-tools-vs-data-tools contract** (UI
  tools change what the user *sees* and return no data; answer from data tools).
  Adding a tool without prompt guidance regresses tool selection.
- Keep tool args model-friendly: flat, typed, sensibly defaulted. Things the
  model must not set (poll intervals, caps) are **module constants**, not args.

## Evals (`tests/evals/`)

`cases/core.yaml` holds golden trajectories; deterministic scorers grade
`tool_selection`, `args`, `length`, `final`.

- **Live gate** `uv run pytest -m eval -s` needs `OPENROUTER_API_KEY` **and** a
  running `langgraph dev` server. It is **not** part of normal CI and **hangs**
  in sandboxes without the server — do not run it to "verify" a change.
- **Offline replay** (`test_replay.py`) re-scores committed **full-trajectory
  snapshots** (`threads.get_state` dumps) with no key/network and **is** part of
  normal `pytest`. The deterministic scorers match on tool names, so
  renaming/removing a tool can break replay; changing a tool's *implementation*
  generally does not. New live cases are CI-safe (they self-skip without the key;
  a missing recording is a soft skip).
- **Unit tests** mock the backend with `httpx.MockTransport` (`test_tools.py`,
  `test_stac_tools.py`).

## Gotchas

- E2E/eval tests **self-skip** without `OPENROUTER_API_KEY`, so a clean local
  `pytest` may be hiding skipped live cases. Check the real summary — piping
  through `grep`/`tail` masks both failures and the skip count.
- Conventional commits; never hand-edit CHANGELOGs (release-please owns them).
