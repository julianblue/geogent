from langchain_core.messages import SystemMessage

from geogent_agent.models import get_chat_model
from geogent_agent.prompts import SYSTEM_PROMPT
from geogent_agent.state import GraphState
from geogent_agent.tools import TOOLS


async def agent_node(state: GraphState) -> dict:
    """Invoke the chat model with tools and the system prompt."""
    model = get_chat_model().bind_tools(TOOLS)
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = await model.ainvoke(messages)
    return {"messages": [response]}
