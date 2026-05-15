#!/usr/bin/env sh
# Apply LangGraph checkpointer schema migrations. Idempotent — safe to run
# on every deploy. Intended as the Railway pre-deploy command for the
# agent service.
#
# The production langgraph image installs the package system-wide and
# strips uv, so we prefer plain `python`. Locally `uv run` is available
# and ensures the dev venv is used.
set -eu

if command -v uv >/dev/null 2>&1; then
  exec uv run python -m geogent_agent.scripts.setup_checkpointer
else
  exec python -m geogent_agent.scripts.setup_checkpointer
fi
