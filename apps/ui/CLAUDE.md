# apps/ui — CLAUDE.md

Next.js App Router front end: the chat + map + insights workspace. Bridges
assistant-ui ↔ the LangGraph agent and proxies REST calls to the backend.

> Big picture: `../../CONTEXT.md`. CI gates: root `../../CLAUDE.md` —
> `pnpm lint && pnpm typecheck && pnpm test && pnpm exec prettier --check .`.
> **Prettier is a separate gate** (not part of `lint`); it also checks Markdown,
> so run it after editing docs here too.

Stack: Next.js (App Router) + TypeScript + Tailwind/shadcn · assistant-ui over a
LangGraph runtime · MapLibre via `react-map-gl` · deck.gl (`MapboxOverlay`) ·
Recharts · vitest/jsdom · pnpm.

## The two bridges

- **Chat ↔ agent:** the `/api/lg/[..._path]` proxy forwards assistant-ui traffic
  to LangGraph. It **stamps `metadata.owner` = session user** and authorizes
  thread-scoped requests **server-side, fail-closed** (a missing/mismatched
  owner or any upstream read error ⇒ not-owned). Per-user isolation lives here,
  not in client filtering.
- **REST ↔ backend:** `/api/proxy/*` route handlers call the backend via
  `lib/api.ts` (`proxyJson`/`backendFetch`), attaching the session JWT. Add a new
  backend call as a **per-endpoint** `route.ts` under `app/api/proxy/...` (mirror
  `proxy/fields/in-bbox/route.ts`).

## Map state & overlays

`components/map/MapStateProvider.tsx` is the **single source of truth**:
viewport, `features`, `fields`, `layers` (`MapLayer[]` with a `LayerSource`
union), `sentinel2Scene`, selected field. Everything map-related reads/writes
here. Two overlay mechanisms:

1. **Imperative MapLibre overlays** (`map/overlays.ts`) — currently just
   buffer, drawn as `${id}-fill` / `${id}-outline` layers. `LayerSync.tsx`
   applies visibility/opacity/z-order keyed off those suffixes;
   `ThreadSnapshotSync` repaints it from `LayerSource` on reopen. (Route and
   isochrone overlays existed here through #55; removed with the agent's
   routing tools — `parseSnapshot` still degrades an old thread's persisted
   `route`/`isochrone` source gracefully rather than crashing on reopen.)
2. **Data-driven deck.gl overlays** (`Sentinel2Overlay.tsx`,
   `AggregationOverlay.tsx`) — each owns a `MapboxOverlay`, attaches on
   `mapReady`, and **reacts to MapState** (no imperative add; visibility/opacity
   read off the `MapLayer`). They no-op through the MapLibre suffix helpers, so
   removal flows via `removeLayer` (state) — `removeOverlay` is harmless for them.

The **Layer Manager** (`LayerManager.tsx`) is generic over `MapLayer[]`, so any
layer registered via `upsertLayer` gets visibility/opacity/reorder/remove for
free. Namespace layer ids by kind (`buffer-`/`aggregation-`/`fieldMemory-`) to
avoid collisions.

## Agent tool integration — the blessed patterns

See the header of `components/assistant-ui/thread.tsx` (which predates the
aggregation client tool). Three patterns, and **do not** use the deprecated
`makeAssistantToolUI`:

- **A — Client tool** (`useAssistantTool` with `execute` + `render`): browser
  performs the side effect and renders inline progress/result (`FlyToTool`,
  `BufferLayerTool`, `FeaturesInViewportTool`, `RenderDashboardTool`,
  `AggregationLayerTool`, `FieldMemoryLayerTool`).
- **B — LangGraph interrupt** (`useLangGraphInterruptState` +
  `useLangGraphSendCommand`): agent calls `interrupt()`, the browser renders an
  approval/render widget and resumes (`ConfirmFeatureSaveTool`,
  `Sentinel2RenderTool`).
- **C — Render-only** for server-executed tools (`useAssistantTool`, no-op
  `execute`): the agent runs it server-side; the browser only renders the result
  (agriculture widgets).

Mount client/interrupt tools in `workspace/AssistantPanel.tsx` (and the
interrupt-driven `Sentinel2RenderTool` in `MapWorkspace.tsx`).

## Widgets & insights

`components/assistant/widgets/` — a typed registry + `widgets/` dir, **dual-mode**
(inline in chat → "Open" → expanded in `InsightsWorkspace`), promoted via
`WorkspaceProvider`. Agent-composed dashboards go through the curated
`render_dashboard` spec (Zod-validated; ADR 0001) — not free-form UI.

## Per-thread snapshot (#20)

`lib/workspaceSnapshot.ts` builds/parses the snapshot stored in LangGraph thread
metadata; `ThreadSnapshotSync` persists and restores it. **`parseSnapshot` is
fail-closed** — every shape is structurally validated (bad layer/source dropped,
garbled viewport ⇒ clean reset). When you add a `LayerSource` kind you must
(a) extend the union in `MapStateProvider`, (b) validate it in `parseLayers`,
and (c) repaint it in `ThreadSnapshotSync` (or, for deck overlays, let the
overlay react to restored `layers`).

## Theming & conventions

- Colors via design tokens: `widgets/viz/chartTheme.ts` uses
  `hsl(var(--token))` so charts theme to light/dark automatically. deck.gl needs
  **concrete RGB** arrays, so map ramps live separately (`map/aggregation.ts`).
- `"use client"` on interactive components.

## Testing

vitest (jsdom). Pure libs have unit tests (`geo`, `workspaceSnapshot`,
`threadListAdapter`, `chatApi`); widgets get render tests. The
"0-width container" Recharts warning in tests is benign. deck.gl is pinned
`^9.3` (GPU aggregation API).
