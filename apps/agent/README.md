# geogent-agent

LangGraph agent that powers the CopilotKit experience in the UI. It calls the
backend via HTTP for all geospatial data access — it does **not** talk to
Postgres directly.

## Stack

- LangGraph + LangChain
- `langgraph-cli` for local dev server (`langgraph dev`)
- Managed with [`uv`](https://docs.astral.sh/uv/)
- `copilotkit` SDK for CopilotKit ↔ LangGraph state-sharing hooks

## Run locally

```bash
uv sync
uv run langgraph dev --port 2024
```

Studio: <http://localhost:2024>

## Layout

```
src/geogent_agent/
├── graph.py          # compiled entrypoint referenced by langgraph.json
├── state.py          # GraphState TypedDict/Pydantic
├── config.py         # pydantic-settings
├── graphs/
│   └── geo_analyst.py  # ReAct-style geospatial analyst graph
├── nodes/              # graph nodes (planner, tool_executor, responder)
├── tools/              # @tool functions (backend_client, geo_tools, osm_tools)
├── prompts/            # system prompts
├── memory/             # checkpointer wiring
├── models/             # chat-model factory
└── utils/
```

## langgraph.json

`langgraph.json` registers the compiled graph under the name `geogent`:

```json
{
  "graphs": { "geogent": "./src/geogent_agent/graph.py:graph" }
}
```
