"""LangSmith tracing helpers shared by graph nodes.

Each node/agent passes the LangGraph ``configurable`` dict and a short
architecture label to ``build_tracing_config`` and splats the result into
``Runnable.with_config(**...)``. The static tags/metadata (provider, model,
architecture) come from the chat-model factory; the dynamic identifiers
(thread_id, assistant_id, user_id) come from LangGraph's ``configurable``.
"""

from __future__ import annotations

from typing import Any

from geogent_agent.models import infer_provider
from geogent_agent.models.chat import _resolve_model_name

_PASSTHROUGH_IDS = ("thread_id", "assistant_id", "user_id")


def build_tracing_config(configurable: dict[str, Any], architecture: str) -> dict[str, Any]:
    """Return ``with_config`` kwargs that tag a run for LangSmith.

    Tags:
      - ``architecture:<name>``
      - ``provider:<openai|anthropic|bedrock|openrouter|unknown>``
      - ``model:<resolved-model-name>``

    Metadata mirrors the tags as keyed fields (so dashboards can group by
    them) and adds any thread/assistant/user IDs LangGraph injected.
    """
    model_name = _resolve_model_name()
    provider = infer_provider(model_name)

    tags = [
        f"architecture:{architecture}",
        f"provider:{provider}",
        f"model:{model_name}",
    ]
    metadata: dict[str, Any] = {
        "architecture": architecture,
        "provider": provider,
        "model": model_name,
    }
    for key in _PASSTHROUGH_IDS:
        value = configurable.get(key)
        if value is not None:
            metadata[key] = value

    return {
        "tags": tags,
        "metadata": metadata,
        "run_name": f"geogent.{architecture}.agent",
    }
