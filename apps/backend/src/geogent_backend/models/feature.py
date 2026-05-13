from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geogent_backend.db.base import Base


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    # server_default mirrors the Python `default=dict` so raw-SQL inserts and
    # alembic autogenerate stay in sync with the schema.
    properties: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
