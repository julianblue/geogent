"""Idempotent migration for the LangGraph Postgres checkpointer.

Creates the configured schema (default: `langgraph`) and runs
`AsyncPostgresSaver.setup()` to apply checkpoint table migrations. Wired
as the Railway release command for the agent service so it runs once per
deploy, not on every container start.
"""

import asyncio

from geogent_agent.memory import run_setup


def main() -> None:
    asyncio.run(run_setup())


if __name__ == "__main__":
    main()
