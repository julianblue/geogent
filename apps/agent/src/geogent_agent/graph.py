"""Compiled LangGraph entrypoint referenced by langgraph.json."""

from geogent_agent.graphs.geo_analyst import build_geo_analyst_graph
from geogent_agent.observability import configure_langsmith

configure_langsmith()

graph = build_geo_analyst_graph().compile()
