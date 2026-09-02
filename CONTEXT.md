# geogent — Repository Context

> The "why" and the big picture. For how to build/test/lint, see the root
> `CLAUDE.md`; for app-specific architecture and conventions, see each app's
> `CLAUDE.md` (`apps/backend`, `apps/agent`, `apps/ui`).

## What geogent is

geogent is **"the geospatial agent"** — an agentic geospatial application for
analytics, insight, and exploration. A user converses with an AI analyst that
can query spatial data, run PostGIS/raster analytics, search satellite imagery,
route and geocode, and **drive a live map + insights workspace** as it works.

The product north star (epic **#27**) is a **generative-UI agent workspace**,
not "a chatbot next to a map":

```
┌─────────────┬───────────────────────────┬──────────────────────┐
│   CHAT      │         MAP CANVAS        │   INSIGHTS WORKSPACE  │
│ assistant-ui│   MapLibre / deck.gl      │  (expandable drawer)  │
│  + inline   │   layers, overlays, draw  │  charts · tables ·    │
│   widgets   │                           │  stat tiles · big map │
└─────────────┴───────────────────────────┴──────────────────────┘
   every tool result is a WIDGET: inline (chat) ──"Open"──▶ expanded (workspace)
```

## Shape of the system

A polyglot monorepo of three independently-deployable services plus a PostGIS
database (see `README.md` for ports and the compose stack):

```
  ┌──────────┐      /api/lg (assistant-ui     ┌──────────────┐
  │   UI     │ ───────  streaming) ─────────▶ │    Agent     │
  │ Next.js  │                                │  LangGraph   │
  └────┬─────┘                                └──────┬───────┘
       │                                             │ HTTP, REST tools
       │  REST  /api/proxy/* ─▶ /api/v1              ▼  (service-user JWT)
       └────────────────────────────────────▶ ┌──────────────┐
                                               │   Backend    │──▶ PostGIS
                                               │   FastAPI    │──▶ STAC / Sentinel-2 COGs
                                               └──────────────┘──▶ OSRM · ORS · Nominatim
```

- **`apps/ui`** — Next.js App Router. Hosts the chat (assistant-ui over a
  LangGraph runtime), the MapLibre/deck.gl canvas, the layer manager, and the
  insights workspace. Talks to the agent through the `/api/lg` proxy and to the
  backend through `/api/proxy/*`.
- **`apps/agent`** — LangGraph ReAct agent. Owns the system prompt and the tool
  set. Tools are **thin**: data tools call the backend over REST; UI tools emit
  render/interrupt actions the browser executes.
- **`apps/backend`** — FastAPI + PostGIS. Owns all data, geometry, raster, and
  external-provider access behind an authenticated `/api/v1`.

## Design principles (the load-bearing ones)

0. **The agent is an agricultural raster analyst, not a general GIS bot.** The
   tool surface is curated for that: imagery, fields, and the analytics over
   them, at four deliberate altitudes (one date → a raw series → an interpreted
   season → per-pixel over time). Breadth that doesn't serve that story is a
   liability — every extra tool costs selection accuracy on the ones that matter.
1. **Thin, stateless agent tools → auth-gated backend.** The agent never holds
   provider URLs, API keys, or DB access. Each data capability is a backend
   `/api/v1` endpoint plus a thin agent tool that calls it with a service-user
   JWT (`geo_tools → /analytics`, `routing_tools → /routing`). This keeps
   secrets server-side and the agent declarative.
2. **UI tools vs data tools.** UI/frontend-action tools change what the user
   *sees* and return **no data**; data tools read from the backend/PostGIS/STAC
   and return facts. The agent must answer from data tools, never from a UI
   tool. This contract is spelled out in the agent's system prompt and is the
   single most important behavioural invariant.
3. **Human-in-the-loop for writes.** Persisting/destructive actions pause via a
   LangGraph `interrupt()` and a UI approval card (`confirm_feature_save` →
   `ApprovalWidget`) — the agent proposes, the user confirms.
4. **Generative UI we own, not free-form UI.** Per **ADR 0001**
   (`docs/adr/0001-agent-ui-components.md`), agent-driven UI is assistant-ui
   Tool UI plus a thin, curated composition layer (`render_dashboard` over Zod
   schemas) — *not* `json-render`/`A2UI`. The agent selects from vetted widgets
   and layouts; it cannot emit arbitrary UI, so every result stays on-brand.
5. **Per-user isolation, fail-closed.** LangGraph threads are stamped with an
   `owner` metadata tag and authorized **server-side** in the `/api/lg` proxy;
   a missing/mismatched owner (or any read error) is treated as not-owned (#50).
6. **A conversation remembers its map.** Each thread persists a workspace
   snapshot (viewport, layers, scene, selection, open widgets) in LangGraph
   thread metadata, restored on reopen (#20). Agent-created overlays carry the
   geometry needed to repaint themselves.

## Capabilities shipped today

- **Accounts & sessions** — JWT auth; multi-conversation thread list with
  per-user scoping; per-thread workspace snapshots.
- **Vector analytics (PostGIS)** — buffer, distance, area, intersects,
  features-within; a stored `features` table with HITL save.
- **Fields/parcels** — field model + **EuroCrops** (Brandenburg) ingestion;
  bbox/crop queries and crop-stats.
- **Raster / imagery** — STAC search (Earth Search), Sentinel-2 L2A COG
  rendering (deck.gl), per-field **zonal stats**, **seasonal index time-series**,
  and **season analysis** (phenology metrics + anomaly vs previous years) over
  eight indices across Sentinel-2 and Landsat. Cloud/shadow/snow is masked
  per-pixel (S2 SCL, Landsat QA_PIXEL) before any statistic is computed.
- **Data cubes / field memory** — multi-date cubes reduced per pixel
  (`field_memory`, `composite`, `trend`, `frequency`) into content-addressed
  server-side artifacts the agent handles as ids, never pixels.
- **Management zones (#65 M3)** — the cube feature stack clustered into
  contiguous agronomic zones with per-zone stats and **driver attribution**
  (which input layer explains the split), shipped as a zone raster plus
  exportable GeoJSON boundaries.
- **Agriculture pack (flagship)** — field selection, zonal stats, NDVI series,
  composite rendering, and agent-composed dashboards.
- **Routing / geocoding (#55)** — backend endpoints for routing, travel-time
  matrix, isochrones and geocoding (OSRM · OpenRouteService · Nominatim). The
  *agent* keeps only forward geocoding: the tool surface was narrowed to the
  agricultural workflows so tool selection stays sharp.
- **Analytics viz (#57)** — deck.gl heatmap & hexbin aggregation layers over the
  feature/field set.
- **Map workspace** — layer manager (visibility/opacity/reorder/remove),
  imperative + deck.gl overlays, insights drawer with Recharts.

## Direction

The live roadmap is **issue #27**. Current priorities (post routing + viz):

- **#58** temporal raster playback (finishes the cheap, high-impact viz tier).
- **#25** change-detection pack (dual-scene swipe, change map/stats).
- **#56** imagery intelligence — SAM feature extraction (#59) and embeddings
  similarity search (#60); the depth differentiator, carrying real ML/infra
  weight.
- Polish: responsive/mobile (#53), global undo/redo (#54).
- Recognised future gaps to be filed by the owner: a **TiTiler** raster-serving
  spike and **vector tiles / PMTiles** for scale.

## Where to look next

- **Build/test/lint gates:** root `CLAUDE.md`.
- **App internals & conventions:** `apps/{backend,agent,ui}/CLAUDE.md`.
- **Architecture & ports:** `README.md`.
- **Agent-UI decision:** `docs/adr/0001-agent-ui-components.md`.
- **Eval harness:** `apps/agent/tests/evals/README.md`.
- **Roadmap / status:** GitHub issue #27.
