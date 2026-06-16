from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    """Shared state for the geogent agent graph.

    `messages` uses LangGraph's `add_messages` reducer so nodes can append
    LangChain messages incrementally.

    `summary` / `summarized_count` back the summarizing trimmer (context
    control): on long threads the agent node folds the oldest
    `summarized_count` messages into `summary` and sends that synopsis plus the
    recent turns to the model. The full `messages` list is never pruned, so the
    UI transcript stays intact — these fields only shape what the model sees.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    summary: NotRequired[str]
    summarized_count: NotRequired[int]
