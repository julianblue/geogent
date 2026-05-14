"""Compiled classic-LangChain graph entrypoint referenced by langgraph.json."""

from geogent_agent.agents.classic_langchain import build_classic_agent_graph
from geogent_agent.observability import configure_langsmith

configure_langsmith()

graph = build_classic_agent_graph()
