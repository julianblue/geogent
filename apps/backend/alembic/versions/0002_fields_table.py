"""fields table

Revision ID: 0002_fields_table
Revises: 0001_initial_schema
Create Date: 2026-05-24 00:00:00.000000

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

# Alembic reads these module-level attributes via reflection; they're not
# referenced anywhere else in this file. Listed in __all__ to keep static
# analyzers (CodeQL py/unused-global-variable) from flagging them.
revision: str = "0002_fields_table"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = ["revision", "down_revision", "branch_labels", "depends_on", "upgrade", "downgrade"]


def upgrade() -> None:
    op.create_table(
        "fields",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("crop", sa.String(length=255), nullable=True),
        sa.Column("season", sa.String(length=255), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="GEOMETRY",
                srid=4326,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fields_name", "fields", ["name"], unique=False)
    # The GiST spatial index on `fields.geometry` is auto-emitted by GeoAlchemy2
    # because the Geometry column defaults to spatial_index=True.


def downgrade() -> None:
    op.drop_index("ix_fields_name", table_name="fields")
    op.drop_table("fields")
