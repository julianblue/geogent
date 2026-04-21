"""Agent-architecture registry.

Each architecture exposes a `build_*_graph()` function that returns a compiled
LangGraph. The registry lets us add new architectures (LangGraph variants,
DeepAgents, etc.) by dropping in a new module and adding one line here.
"""

from collections.abc import Callable
from typing import Any

from geogent_agent.agents.classic_langchain import build_classic_agent_graph

# name → builder that returns a compiled graph
_REGISTRY: dict[str, Callable[[], Any]] = {
    "classic_langchain": build_classic_agent_graph,
}


def build_agent_graph(name: str) -> Any:
    """Return a compiled LangGraph for the named architecture."""
    try:
        builder = _REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise ValueError(
            f"Unknown agent architecture {name!r}. Available: {available}"
        ) from exc
    return builder()


def available_architectures() -> list[str]:
    return sorted(_REGISTRY)


__all__ = ["build_agent_graph", "available_architectures"]
