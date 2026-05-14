"""Tests for the Postgres checkpointer factory in ``geogent_agent.memory``.

These tests cover the pool wiring (config flags, schema-pinning configure
callback, missing-DSN error path) without requiring a live Postgres
instance. End-to-end persistence is verified manually via the steps in
apps/agent/README.md → Persistence.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from geogent_agent.config import get_settings
from geogent_agent.memory import _configure, build_pool


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_build_pool_raises_when_dsn_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="AGENT_DATABASE_URL"):
        build_pool()


async def test_build_pool_configures_psycopg_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://geogent:geogent@localhost:5432/geogent")
    monkeypatch.setenv("AGENT_DB_POOL_MIN", "2")
    monkeypatch.setenv("AGENT_DB_POOL_MAX", "8")

    pool = build_pool()
    try:
        # AsyncPostgresSaver requires autocommit + dict_row to function
        # correctly; prepare_threshold=0 disables server-side prepared
        # statements which the saver cannot use across pooled connections.
        assert pool.kwargs["autocommit"] is True
        assert pool.kwargs["prepare_threshold"] == 0
        from psycopg.rows import dict_row

        assert pool.kwargs["row_factory"] is dict_row
        assert pool.min_size == 2
        assert pool.max_size == 8
        # Factory must not open the pool — opener owns the lifecycle.
        # `closed` is the public flag (True until `open()` is awaited).
        assert pool.closed is True
    finally:
        await pool.close()


async def test_configure_pins_search_path_to_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_DATABASE_URL", "postgresql://geogent:geogent@localhost:5432/geogent")
    monkeypatch.setenv("AGENT_DB_SCHEMA", "langgraph_test")

    conn = MagicMock()
    conn.set_autocommit = AsyncMock()
    cursor = AsyncMock()
    cursor_ctx = MagicMock()
    cursor_ctx.__aenter__ = AsyncMock(return_value=cursor)
    cursor_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.cursor = MagicMock(return_value=cursor_ctx)

    await _configure(conn)

    conn.set_autocommit.assert_awaited_once_with(True)
    cursor.execute.assert_awaited_once()
    # `_configure` passes a psycopg.sql.Composed; rendering it verifies that
    # the schema name is safely quoted via Identifier (defeats injection
    # via a `"` or backslash in AGENT_DB_SCHEMA).
    stmt = cursor.execute.await_args.args[0]
    rendered = stmt.as_string(None)
    assert rendered == 'SET search_path TO "langgraph_test", public'
