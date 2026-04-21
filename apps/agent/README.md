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
├── graph.py            # compiled entrypoint for the LangGraph ReAct agent
├── classic_graph.py    # compiled entrypoint for the classic-LangChain agent
├── state.py            # GraphState TypedDict (shared messages state)
├── config.py           # pydantic-settings
├── graphs/
│   └── geo_analyst.py  # ReAct-style geospatial analyst graph
├── agents/             # non-graph architectures (classic LangChain, DeepAgents, …)
│   ├── __init__.py     # registry: build_agent_graph(name)
│   └── classic_langchain.py
├── nodes/              # graph nodes
├── tools/              # @tool functions (backend_client, geo_tools, osm_tools)
├── prompts/            # system prompts
├── memory/             # checkpointer wiring
├── models/             # chat-model factory (Anthropic, OpenAI, Bedrock)
└── utils/
```

## Architectures

The agent app is a test bed for multiple architectures served uniformly by
`langgraph dev`. Non-graph agents (like the classic `AgentExecutor`) are
wrapped in a single-node LangGraph so they share the same serving surface.

| Name                 | Graph ID (in `langgraph.json`) | Where it lives                         | Default LLM                                |
| -------------------- | ------------------------------ | -------------------------------------- | ------------------------------------------ |
| LangGraph ReAct      | `geogent`                      | `graphs/geo_analyst.py`                | `AGENT_MODEL` (Anthropic / OpenAI)         |
| Classic LangChain    | `geogent-classic`              | `agents/classic_langchain.py`          | `BEDROCK_MODEL_ID` via `ChatBedrockConverse` |
| DeepAgents (planned) | `geogent-deep`                 | `agents/deep_agent.py` (not yet)       | TBD                                        |

Add a new architecture by dropping a module in `agents/`, exposing a
`build_*_graph()` that returns a compiled graph, and registering it in
`agents/__init__.py` plus `langgraph.json`.

## langgraph.json

```json
{
  "graphs": {
    "geogent": "./src/geogent_agent/graph.py:graph",
    "geogent-classic": "./src/geogent_agent/classic_graph.py:graph"
  }
}
```

## Amazon Bedrock

The classic-LangChain architecture uses `ChatBedrockConverse` from
`langchain-aws`. Credentials come from the **standard boto3 chain** —
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` env vars,
`~/.aws/credentials`, or an instance/task IAM role. Region is controlled by
`AWS_REGION` (default `us-east-1`) and the model ID by `BEDROCK_MODEL_ID`
(default `us.anthropic.claude-sonnet-4-5-20250929-v1:0`).

`get_chat_model()` also accepts Bedrock model IDs directly — any name
beginning with `anthropic.`, `us.anthropic.`, or the explicit `bedrock:`
prefix is routed through Bedrock.
