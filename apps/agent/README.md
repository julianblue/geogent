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
├── tools/              # @tool functions (backend_client, geo_tools, osm_tools, stac_tools)
├── prompts/            # system prompts
├── memory/             # checkpointer wiring
├── models/             # chat-model factory (Anthropic, OpenAI, Bedrock)
└── utils/
```

## Architectures

The agent app is a test bed for multiple architectures served uniformly by
`langgraph dev`. Non-graph agents (like the classic `AgentExecutor`) are
wrapped in a single-node LangGraph so they share the same serving surface.

| Name                 | Graph ID (in `langgraph.json`) | Where it lives                         | Default LLM            |
| -------------------- | ------------------------------ | -------------------------------------- | ---------------------- |
| LangGraph ReAct      | `geogent`                      | `graphs/geo_analyst.py`                | `AGENT_MODEL`          |
| Classic LangChain    | `geogent-classic`              | `agents/classic_langchain.py`          | `AGENT_MODEL`          |
| DeepAgents (planned) | `geogent-deep`                 | `agents/deep_agent.py` (not yet)       | TBD                    |

Both architectures pick their LLM from the same `AGENT_MODEL` env var via
`get_chat_model()`. Provider is inferred from the model name prefix:
`openrouter:<vendor>/<model>` → OpenRouter (OpenAI-compatible gateway);
`bedrock:` / `anthropic.` / `us.anthropic.` → AWS Bedrock; `claude-*` →
Anthropic API; `gpt-*` → OpenAI.

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

To use AWS Bedrock, set `AGENT_MODEL` to a Bedrock model ID — any name
beginning with `anthropic.`, `us.anthropic.`, or the explicit `bedrock:`
prefix is routed to `ChatBedrockConverse` from `langchain-aws`. Credentials
come from the **standard boto3 chain** — `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` env vars,
`~/.aws/credentials`, or an instance/task IAM role. Region is controlled by
`AWS_REGION` (default `us-east-1`).

For backward compatibility, if `BEDROCK_MODEL_ID` is set but `AGENT_MODEL`
is not, the model factory falls back to `BEDROCK_MODEL_ID` instead of the
default Anthropic-API model. New configurations should set `AGENT_MODEL`.

## OpenRouter

[OpenRouter](https://openrouter.ai) is an OpenAI-compatible gateway that
fronts many providers behind a single key. Use it by setting
`OPENROUTER_API_KEY` and an `AGENT_MODEL` with the `openrouter:` prefix:

```bash
OPENROUTER_API_KEY=sk-or-…
AGENT_MODEL=openrouter:anthropic/claude-3.5-sonnet
```

The model name after the prefix is passed through verbatim as the
OpenRouter model slug (see <https://openrouter.ai/models>). The base URL
defaults to `https://openrouter.ai/api/v1` and can be overridden with
`OPENROUTER_BASE_URL`. Routing goes through `ChatOpenAI` from
`langchain-openai` with the OpenRouter `base_url` — no new dependency.

## Observability (LangSmith)

The agent traces runs to [LangSmith](https://smith.langchain.com) when
`LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are set on the process.
Configuration lives in the environment (compose, Railway, shell) — the
LangChain tracer reads `LANGSMITH_*` directly, so `.env` files work too.
`Settings.langsmith_*` mirrors the env vars for diagnostics but never
mutates `os.environ` (mutating it after `langchain_core` imports is too late
to matter, so the project avoids the footgun).

On startup the agent logs one line:

```
LangSmith tracing enabled project=geogent-dev
LangSmith tracing disabled (set LANGSMITH_TRACING=true to enable)
```

It also warns when `LANGSMITH_TRACING=true` but the API key is missing —
the tracer silently drops spans in that case, which is easy to miss.

### Run-name and tag conventions

Each LLM invocation is wrapped in `.with_config(...)` with these fields:

| Field      | Value                                                                                 |
| ---------- | ------------------------------------------------------------------------------------- |
| `run_name` | `geogent.<architecture>.agent`                                                        |
| tags       | `architecture:…`, `provider:…`, `model:…`                                             |
| metadata   | same keys as tags, plus `thread_id` / `assistant_id` / `user_id` when LangGraph passes them in `configurable`. |

`architecture` is `langgraph_react` or `classic_langchain`. `provider` is
inferred from the model-name prefix (`anthropic`, `openai`, `bedrock`,
`openrouter`). Filter the LangSmith UI on these tags to compare runs across
architectures or providers without hunting through run names.

### Useful env knobs

| Variable                                   | Purpose                                  |
| ------------------------------------------ | ---------------------------------------- |
| `LANGSMITH_PROJECT`                        | Per-environment project name             |
| `LANGSMITH_ENDPOINT`                       | EU or self-hosted LangSmith URL          |
| `LANGSMITH_SAMPLING_RATE`                  | Sample a fraction (0.0–1.0) of runs. Read by the `langsmith` client directly — the agent surfaces it as a knob but does not interpret the value itself. |
| `LANGSMITH_HIDE_INPUTS` / `..._OUTPUTS`    | Redact request/response bodies in traces. Also enforced client-side by `langsmith`. |

## Tools

The agent ships three groups of tools, all wired into both the
`geogent` and `geogent-classic` graphs:

- **Backend (`geo_tools`)** — `list_features`, `buffer_geometry`,
  `distance_between`, `area_of`, `geometries_intersect`,
  `features_within`. Each calls the FastAPI backend and runs in PostGIS.
- **Geocoding (`osm_tools`)** — `geocode_place` against OpenStreetMap
  Nominatim (no auth required).
- **STAC (`stac_tools`)** — `stac_list_collections`, `stac_search`,
  `stac_get_item`. All accept an optional `api_url` (default Earth Search
  v1: `https://earth-search.aws.element84.com/v1`), so the agent can
  point at any STAC-compliant endpoint per call.
