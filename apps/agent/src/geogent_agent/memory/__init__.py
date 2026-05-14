"""Checkpointer wiring.

The production LangGraph runtime (`langgraph build`-produced image) reads
`POSTGRES_URI` and applies its own Postgres saver — the graphs in
`graph.py` / `classic_graph.py` therefore compile with no checkpointer
arg. `run_setup()` here is invoked once per Railway deploy via
`scripts/setup_checkpointer.py` to create the dedicated schema and apply
idempotent checkpoint-table migrations.

`langgraph dev` overrides any compiled-in checkpointer with its own
in-memory saver (see langchain-ai/langgraph#5790), so do not try to
attach one there.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection, sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from geogent_agent.config import get_settings


async def _configure(conn: AsyncConnection) -> None:
    # Pin search_path so AsyncPostgresSaver's unschema-qualified SQL lands
    # in our dedicated schema instead of `public`. psycopg.sql.Identifier
    # handles quoting so an exotic schema name can't escape the literal.
    await conn.set_autocommit(True)
    schema = get_settings().agent_db_schema
    stmt = sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))
    async with conn.cursor() as cur:
        await cur.execute(stmt)


def build_pool() -> AsyncConnectionPool:
    s = get_settings()
    if not s.agent_database_url:
        raise RuntimeError("AGENT_DATABASE_URL is required for the Postgres checkpointer")
    return AsyncConnectionPool(
        conninfo=s.agent_database_url,
        min_size=s.agent_db_pool_min,
        max_size=s.agent_db_pool_max,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=_configure,
        open=False,
    )


async def run_setup() -> None:
    s = get_settings()
    pool = build_pool()
    await pool.open()
    try:
        create_schema = sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
            sql.Identifier(s.agent_db_schema)
        )
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(create_schema)
        await AsyncPostgresSaver(conn=pool).setup()
    finally:
        await pool.close()
