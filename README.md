# geogent

Agentic geospatial application for analytics, insights, and exploration.

`geogent` is a polyglot monorepo organized as three independently-deployable services:

| App             | Stack                                                                 | Port  |
| --------------- | --------------------------------------------------------------------- | ----- |
| `apps/ui`       | Next.js (App Router) + TypeScript + Tailwind + CopilotKit + MapLibre  | 3000  |
| `apps/backend`  | FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + GeoAlchemy2 + Alembic| 8000  |
| `apps/agent`    | LangChain + LangGraph (LangGraph Platform layout)                     | 2024  |
| `db` (compose)  | Postgres 16 + PostGIS 3.4                                             | 5432  |

## Architecture

```
  ┌──────────┐     /api/copilotkit      ┌──────────────┐
  │   UI     │ ───────────────────────▶ │    Agent     │
  │ Next.js  │      CopilotRuntime      │  LangGraph   │
  └────┬─────┘                          └──────┬───────┘
       │                                        │ HTTP (tools)
       │   REST /api/v1                         ▼
       │                                 ┌──────────────┐
       └────────────────────────────────▶│   Backend    │
                                         │   FastAPI    │
                                         └──────┬───────┘
                                                │ asyncpg
                                                ▼
                                         ┌──────────────┐
                                         │  PostGIS DB  │
                                         └──────────────┘
```

The **backend** owns persistence, auth, and all PostGIS queries. The **agent** is
stateless over HTTP — its LangChain tools call backend endpoints rather than
talking to Postgres directly. The **UI** hosts a CopilotKit runtime that proxies
chat traffic to the agent, and also calls the backend directly for data fetches.

## Quickstart

### Prerequisites

- Docker + Docker Compose
- Node.js 20+ and `pnpm`
- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- An LLM API key (Anthropic or OpenAI)

### Clone and configure

```bash
git clone <repo-url> geogent && cd geogent
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY (or OPENAI_API_KEY)
```

### Run the full stack with Docker Compose

```bash
docker compose up --build
```

This starts PostGIS, the backend, the agent, and the UI. Open:

- UI: <http://localhost:3000>
- Backend docs: <http://localhost:8000/docs>
- LangGraph studio: <http://localhost:2024>

### Run services natively (faster iteration)

```bash
# Database only
docker compose up db

# Backend
cd apps/backend
uv sync
uv run alembic upgrade head
uv run uvicorn geogent_backend.main:app --reload --port 8000

# Agent (new terminal)
cd apps/agent
uv sync
uv run langgraph dev --port 2024

# UI (new terminal)
cd apps/ui
pnpm install
pnpm dev
```

### Common tasks

```bash
make up        # docker compose up --build
make down      # docker compose down
make fmt       # run all formatters
make test      # run all tests
```

## Repository layout

```
geogent/
├── apps/
│   ├── ui/          # Next.js + CopilotKit
│   ├── backend/     # FastAPI + PostGIS
│   └── agent/       # LangChain + LangGraph
├── scripts/         # db init, dev bootstrap
├── docker-compose.yml
├── Makefile
└── .env.example
```

See each app's own `README.md` (or source tree) for service-specific details.
