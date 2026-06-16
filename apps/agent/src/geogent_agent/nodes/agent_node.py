import json
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from geogent_agent.config import get_settings
from geogent_agent.models import get_chat_model
from geogent_agent.prompts import SYSTEM_PROMPT
from geogent_agent.state import GraphState
from geogent_agent.tools import TOOLS
from geogent_agent.utils.context import (
    render_messages,
    summarize_and_partition,
    trim_history,
)
from geogent_agent.utils.tracing import build_tracing_config

_SUMMARY_INSTRUCTION = (
    "You compress earlier turns of a geospatial-analyst conversation into a "
    "concise running summary. Preserve durable facts the assistant will still "
    "need: the user's goal, resolved places/coordinates/field ids, what tools "
    "ran and their key results, and any decisions or pending intent. Drop "
    "pleasantries. Return only the updated summary as plain prose."
)


async def _summarize_history(prior_summary: str, new_messages: list[AnyMessage]) -> str:
    """Default summarizer: fold newly-dropped turns into the running summary.

    Uses the chat model WITHOUT tools (we want prose, not tool calls). Kept
    incremental — only the new messages plus the prior summary are sent."""
    rendered = render_messages(new_messages)
    prior_block = f"Summary so far:\n{prior_summary}\n\n" if prior_summary else ""
    response = await get_chat_model().ainvoke(
        [
            SystemMessage(content=_SUMMARY_INSTRUCTION),
            HumanMessage(content=f"{prior_block}New turns to fold in:\n{rendered}"),
        ]
    )
    return response.content if isinstance(response.content, str) else str(response.content)


def _format_map_state(map_state: Any) -> str:
    """Pretty-print the UI-supplied map context for the system message."""
    try:
        rendered = json.dumps(map_state, indent=2, default=str)
    except (TypeError, ValueError):
        rendered = repr(map_state)
    return f"\n\nCurrent map_state (from config.configurable):\n{rendered}"


def _today_block() -> str:
    """Inject the current UTC date so the model doesn't dismiss STAC results
    whose datetime is past its training cutoff as 'synthetic test data'.

    Sentinel-2 catalog returns scenes acquired up to ~3 days ago; without this
    anchor the LLM has been observed constraining searches back to its
    training horizon and reporting 'no recent imagery'.
    """
    return f"\n\nToday's date is {datetime.now(UTC):%Y-%m-%d} (UTC). Trust STAC datetimes."


async def agent_node(state: GraphState, config: RunnableConfig | None = None) -> dict:
    """Invoke the chat model with tools, the system prompt, and any UI map context."""
    configurable = (config or {}).get("configurable") or {}
    model = (
        get_chat_model()
        .bind_tools(TOOLS)
        .with_config(**build_tracing_config(configurable, architecture="langgraph_react"))
    )

    system_content = SYSTEM_PROMPT + _today_block()
    map_state = configurable.get("map_state")
    if map_state:
        system_content += _format_map_state(map_state)

    # Bound history growth on long threads. The full message list is never
    # pruned (the UI renders it); we only shape what the model receives. When
    # summarization is enabled, dropped turns are folded into a running summary;
    # otherwise they're trimmed away (drop-only).
    settings = get_settings()
    budget = settings.agent_max_history_tokens
    update: dict[str, Any] = {}
    if settings.agent_history_summarize:
        history, summary, summarized_count = await summarize_and_partition(
            state["messages"],
            state.get("summary", ""),
            state.get("summarized_count", 0),
            budget,
            _summarize_history,
        )
        update["summary"] = summary
        update["summarized_count"] = summarized_count
        if summary:
            system_content += f"\n\nSummary of earlier turns (condensed):\n{summary}"
    else:
        history = trim_history(state["messages"], budget)

    messages = [SystemMessage(content=system_content), *history]
    response = await model.ainvoke(messages)
    return {"messages": [response], **update}
