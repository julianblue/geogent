"""Compiled LangGraph entrypoint referenced by langgraph.json."""

from geogent_agent.graphs.geo_analyst import build_geo_analyst_graph

graph = build_geo_analyst_graph().compile()
