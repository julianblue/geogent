from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from geogent_backend.config import get_settings
from geogent_backend.db.base import Base
from geogent_backend.models import *  # noqa: F401,F403  (register models for autogen)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = Base.metadata


# PostGIS extension tables/schemas that autogen would otherwise try to drop or
# re-create. Keep migrations focused on application tables only; extension
# objects are owned by scripts/db/init-postgis.sql.
_POSTGIS_SCHEMAS = frozenset({"tiger", "tiger_data", "topology"})
_POSTGIS_TABLES = frozenset(
    {
        "spatial_ref_sys",
        "geography_columns",
        "geometry_columns",
        "raster_columns",
        "raster_overviews",
    }
)


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001 - alembic signature
    if type_ == "table":
        if name in _POSTGIS_TABLES:
            return False
        schema = getattr(obj, "schema", None)
        if schema in _POSTGIS_SCHEMAS:
            return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=False,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=False,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
