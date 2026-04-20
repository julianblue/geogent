from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from geogent_agent.nodes.agent_node import agent_node
from geogent_agent.state import GraphState
from geogent_agent.tools import TOOLS


def build_geo_analyst_graph() -> StateGraph:
    """A ReAct-style loop: agent ↔ tools, until the agent stops calling tools."""
    graph = StateGraph(GraphState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    graph.add_edge("agent", END)

    return graph
