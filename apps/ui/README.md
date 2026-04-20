# geogent-ui

Next.js 14 (App Router) front-end. Hosts a MapLibre map and the CopilotKit
sidebar, and exposes `/api/copilotkit` as the CopilotRuntime endpoint that
proxies chat traffic to the LangGraph agent.

## Stack

- Next.js 14 App Router + TypeScript
- Tailwind CSS
- CopilotKit (`@copilotkit/react-core`, `@copilotkit/react-ui`, `@copilotkit/runtime`)
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
│   ├── layout.tsx               # wraps <CopilotKit runtimeUrl="/api/copilotkit">
│   ├── page.tsx                 # MapView + CopilotSidebar
│   ├── globals.css
│   └── api/copilotkit/route.ts  # CopilotRuntime → LangGraph agent
├── components/
│   ├── map/MapView.tsx          # react-map-gl + MapLibre
│   └── copilot/                 # useCopilotAction hooks
├── lib/                         # api + utils helpers
└── types/
```
