"""Compiled classic-LangChain graph entrypoint referenced by langgraph.json."""

from geogent_agent.agents.classic_langchain import build_classic_agent_graph

graph = build_classic_agent_graph()
