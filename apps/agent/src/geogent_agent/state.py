from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    """Shared state for the geogent agent graph.

    `messages` uses LangGraph's `add_messages` reducer so nodes can append
    LangChain messages incrementally.
    """

    messages: Annotated[list[AnyMessage], add_messages]
