"""Drive the live agent to produce a trajectory dict.

This is the *only* eval module that talks to a running agent. It runs one case
as a single chat turn against a `langgraph dev` server (booted by the shared
``langgraph_server`` fixture) and returns the raw ``threads.get_state`` dict.
Everything downstream — the scorers, the report — consumes that dict, so they
stay offline and unit-testable.
"""

from __future__ import annotations

from typing import Any

from langgraph_sdk import get_client

from tests.evals.dataset import EvalCase

GRAPH_ID = "geogent"


async def run_case(base_url: str, case: EvalCase) -> dict[str, Any]:
    """Run a single eval case and return its trajectory dict."""
    client = get_client(url=base_url)
    thread = await client.threads.create()
    await client.runs.wait(
        thread["thread_id"],
        GRAPH_ID,
        input={"messages": [{"role": "user", "content": case.input}]},
        config={"configurable": case.configurable},
    )
    return await client.threads.get_state(thread["thread_id"])
