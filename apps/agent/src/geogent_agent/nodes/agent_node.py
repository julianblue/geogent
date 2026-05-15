import json
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from geogent_agent.models import get_chat_model
from geogent_agent.prompts import SYSTEM_PROMPT
from geogent_agent.state import GraphState
from geogent_agent.tools import TOOLS


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
    model = get_chat_model().bind_tools(TOOLS)

    system_content = SYSTEM_PROMPT + _today_block()
    configurable = (config or {}).get("configurable") or {}
    map_state = configurable.get("map_state")
    if map_state:
        system_content += _format_map_state(map_state)

    messages = [SystemMessage(content=system_content), *state["messages"]]
    response = await model.ainvoke(messages)
    return {"messages": [response]}
