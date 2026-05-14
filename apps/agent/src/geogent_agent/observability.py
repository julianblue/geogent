"""LangSmith observability setup.

The LangChain tracer reads `LANGSMITH_*` directly from `os.environ` at import
time, so this module deliberately does NOT mutate the environment — operators
configure tracing by setting env vars on the process (compose, Railway,
shell). What this module does:

- Validates the configuration on first import.
- Emits one log line describing the resulting state.
- Warns when `LANGSMITH_TRACING=true` but no API key is present (the tracer
  silently drops spans in that case, which is easy to miss).

Imported from `graph.py` and `classic_graph.py` so the diagnostic fires once
per `langgraph dev` boot. A module-level guard keeps the message from
repeating across hot-reloads within the same process.
"""

from __future__ import annotations

import logging
import os
from functools import cache

from geogent_agent.config import get_settings

_logger = logging.getLogger("geogent_agent.observability")


def _is_tracing_enabled() -> bool:
    """Treat the canonical `LANGSMITH_TRACING` and the legacy
    `LANGCHAIN_TRACING_V2` as equivalent — LangChain accepts either.
    """
    raw = os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2")
    return str(raw).lower() in {"1", "true", "yes", "on"}


@cache
def configure_langsmith() -> None:
    """Validate LangSmith environment and log a single status line.

    Cached so repeat calls in the same process are no-ops; both `graph.py`
    and `classic_graph.py` import this module so the cache dedupes that
    pair. A `langgraph dev` hot-reload re-imports the module and resets
    the cache, so the operator sees one fresh status line per reload —
    not silence forever. Tests reset via `configure_langsmith.cache_clear()`.
    """
    settings = get_settings()

    enabled = _is_tracing_enabled()
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    project = os.environ.get("LANGSMITH_PROJECT") or settings.langsmith_project
    endpoint = os.environ.get("LANGSMITH_ENDPOINT") or settings.langsmith_endpoint

    if not enabled:
        _logger.info("LangSmith tracing disabled (set LANGSMITH_TRACING=true to enable)")
        return

    if not api_key:
        _logger.warning(
            "LANGSMITH_TRACING=true but LANGSMITH_API_KEY is unset; traces will be dropped silently"
        )
        return

    endpoint_suffix = f" endpoint={endpoint}" if endpoint else ""
    _logger.info("LangSmith tracing enabled project=%s%s", project, endpoint_suffix)
