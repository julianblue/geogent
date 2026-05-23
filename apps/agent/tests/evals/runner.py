"""Drive the live agent to produce a trajectory dict.

This is the *only* eval module that talks to a running agent. It runs one case
as a single chat turn against a `langgraph dev` server (booted by the shared
``langgraph_server`` fixture) and returns the raw ``threads.get_state`` dict.
Everything downstream — the scorers, the report — consumes that dict, so they
stay offline and unit-testable.

Two of the agent's tools (``show_sentinel2_scene`` and ``confirm_feature_save``)
call LangGraph's ``interrupt()`` and pause the run waiting for the UI. In the
browser the user clicks Save / the scene renders and the UI resumes the graph
with a result payload. Here we stand in for the UI: when a run pauses, we feed
back a canned success payload (matching each tool's documented resume shape) and
continue, so the agent reaches a final answer we can grade.
"""

from __future__ import annotations

from typing import Any

from langgraph_sdk import get_client

from tests.evals.dataset import EvalCase

GRAPH_ID = "geogent"

# How many interrupts we'll auto-resume before giving up (guards a misbehaving
# loop; the richest workflow — show then save — needs at most a couple).
MAX_RESUMES = 6


def _pending_interrupts(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Interrupt objects ({value, id}) currently blocking the thread."""
    interrupts: list[dict[str, Any]] = list(state.get("interrupts") or [])
    for task in state.get("tasks") or []:
        if isinstance(task, dict):
            interrupts.extend(task.get("interrupts") or [])
    return [i for i in interrupts if isinstance(i, dict)]


def _canned_resume(interrupt: dict[str, Any]) -> dict[str, Any]:
    """Stand in for the UI's resume payload, keyed on the interrupt type.

    Shapes mirror the tool docstrings in ``tools/frontend_actions.py``:
    ``show_sentinel2_scene`` resumes with ``{ok, item_id, datetime, cloud_cover}``
    and ``confirm_feature_save`` with ``{ok, id}``.
    """
    value = interrupt.get("value")
    kind = value.get("type") if isinstance(value, dict) else None
    if kind == "show_sentinel2_scene":
        item_id = (value or {}).get("item_id") or "S2B_31UDQ_20260501_0_L2A"
        return {
            "ok": True,
            "item_id": item_id,
            "datetime": "2026-05-01T10:30:00Z",
            "cloud_cover": 4.2,
        }
    if kind == "confirm_feature_save":
        return {"ok": True, "id": 4242}
    # Unknown interrupt: a generic success keeps the graph moving.
    return {"ok": True}


async def run_case(base_url: str, case: EvalCase) -> dict[str, Any]:
    """Run a single eval case (auto-resuming any interrupts) and return its state."""
    client = get_client(url=base_url)
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    await client.runs.wait(
        thread_id,
        GRAPH_ID,
        input={"messages": [{"role": "user", "content": case.input}]},
        config={"configurable": case.configurable},
    )
    state = await client.threads.get_state(thread_id)

    resumes = 0
    while (pending := _pending_interrupts(state)) and resumes < MAX_RESUMES:
        await client.runs.wait(thread_id, GRAPH_ID, command={"resume": _canned_resume(pending[0])})
        state = await client.threads.get_state(thread_id)
        resumes += 1

    return state
