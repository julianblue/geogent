"""raster jobs + stat cache

Revision ID: 0003_raster_jobs
Revises: 0002_fields_table
Create Date: 2026-05-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic reads these module-level attributes via reflection; they're not
# referenced anywhere else in this file. Listed in __all__ to keep static
# analyzers (CodeQL py/unused-global-variable) from flagging them.
revision: str = "0003_raster_jobs"
down_revision: str | None = "0002_fields_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["revision", "down_revision", "branch_labels", "depends_on", "upgrade", "downgrade"]


def upgrade() -> None:
    op.create_table(
        "raster_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("field_id", sa.Integer(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "raster_stat_cache",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("histogram", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("cache_key"),
    )


def downgrade() -> None:
    op.drop_table("raster_stat_cache")
    op.drop_table("raster_jobs")
