from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from geogent_agent.nodes.agent_node import agent_node
from geogent_agent.state import GraphState
from geogent_agent.tools import TOOLS


def _format_tool_error(error: Exception) -> str:
    """Render any tool exception as a self-describing string the LLM can
    reason about. The default ToolNode handler only catches ``ToolInvocationError``
    and re-raises everything else, which kills the run; we want the LLM to see
    the error as a ``tool`` message and retry with a fixed payload.
    """
    return f"Tool raised {type(error).__name__}: {error}"


def build_geo_analyst_graph() -> StateGraph:
    """A ReAct-style loop: agent ↔ tools, until the agent stops calling tools."""
    graph = StateGraph(GraphState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS, handle_tool_errors=_format_tool_error))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.add_edge("agent", END)

    return graph
