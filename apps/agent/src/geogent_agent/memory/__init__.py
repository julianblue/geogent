"""Checkpointer and store wiring.

When running via `langgraph dev` or LangGraph Platform, a default in-memory
checkpointer is provided. For production, swap in a Postgres checkpointer
(langgraph.checkpoint.postgres) here and attach it via `graph.compile(
checkpointer=...)`.
"""
