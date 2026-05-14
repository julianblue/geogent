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


def test_build_pool_configures_psycopg_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENT_DATABASE_URL", "postgresql://geogent:geogent@localhost:5432/geogent"
    )
    monkeypatch.setenv("AGENT_DB_POOL_MIN", "2")
    monkeypatch.setenv("AGENT_DB_POOL_MAX", "8")

    pool = build_pool()

    # AsyncPostgresSaver requires autocommit + dict_row to function
    # correctly; prepare_threshold=0 disables server-side prepared
    # statements which the saver cannot use across pooled connections.
    assert pool.kwargs["autocommit"] is True
    assert pool.kwargs["prepare_threshold"] == 0
    from psycopg.rows import dict_row

    assert pool.kwargs["row_factory"] is dict_row
    assert pool.min_size == 2
    assert pool.max_size == 8
    # Pool must not be opened by the factory — opener owns the lifecycle.
    assert not pool._opened  # type: ignore[attr-defined]


async def test_configure_pins_search_path_to_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENT_DATABASE_URL", "postgresql://geogent:geogent@localhost:5432/geogent"
    )
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
    sql = cursor.execute.await_args.args[0]
    assert 'SET search_path TO "langgraph_test"' in sql
    assert "public" in sql
