# geogent-ui

Next.js 14 (App Router) front-end. Hosts a MapLibre map and an assistant-ui
chat panel, and exposes `/api/lg` as the proxy route that forwards chat traffic
to the LangGraph agent.

## Stack

- Next.js 14 App Router + TypeScript
- Tailwind CSS
- assistant-ui (`@assistant-ui/react`, `@assistant-ui/react-langgraph`)
- LangGraph SDK (`@langchain/langgraph-sdk`)
- MapLibre GL JS via `react-map-gl`

## Run locally

```bash
cp .env.local.example .env.local
pnpm install
pnpm dev
```

Open <http://localhost:3000>.

## Layout

```
src/
├── app/
│   ├── layout.tsx                   # root layout
│   ├── app/page.tsx                 # MapView + assistant-ui chat panel
│   ├── globals.css
│   └── api/lg/[..._path]/route.ts   # LangGraph proxy → agent
├── components/
│   ├── assistant/
│   │   ├── RuntimeProvider.tsx      # useLangGraphRuntime + /api/lg client
│   │   ├── Thread.tsx               # assistant-ui chat thread
│   │   └── tools/                   # frontend tool handlers (see below)
│   ├── copilot/cards/               # interrupt UI cards (moves to assistant/widgets in #16)
│   └── map/MapView.tsx              # react-map-gl + MapLibre
├── lib/                             # chatApi (LangGraph SDK client) + helpers
└── types/
```

> **Note:** `components/copilot/cards/` is the current home of the interrupt UI
> cards. Issue #16 renames it to `components/assistant/widgets/` and updates the
> import paths in `components/assistant/tools/`; this doc tracks the path until
> that lands.

## Widget framework + agent tool patterns

Frontend tools are defined server-side in
`apps/agent/src/geogent_agent/tools/frontend_actions.py` and handled in the
browser under `components/assistant/tools/`. Interactive interrupt widgets live
under `components/copilot/cards/` (to be renamed in #16). There are two
distinct mechanisms:

### 1. Client tools (`useAssistantTool`)

The agent emits a tool call, the browser executes it via `useAssistantTool`
(`@assistant-ui/react`) and returns a structured result inline — no graph
pause. These are fire-and-acknowledge side effects on the map:

- `fly_to` → `FlyToTool.tsx`
- `add_buffer_layer` → `BufferLayerTool.tsx`
- `list_features_in_viewport` → `FeaturesInViewportTool.tsx`

### 2. LangGraph interrupts (`interrupt()`)

The tool calls LangGraph's server-side `interrupt()`, pausing the graph until
the user acts. The UI reads the pending interrupt with `useLangGraphInterruptState`,
renders a card, and resumes the graph with `useLangGraphSendCommand`
(`@assistant-ui/react-langgraph`):

- `confirm_feature_save` → `ConfirmFeatureSaveTool.tsx` (Save / Cancel card)
- `show_sentinel2_scene` → `Sentinel2RenderTool.tsx` (deck.gl COG render)
