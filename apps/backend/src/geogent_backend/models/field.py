from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from geogent_backend.db.base import Base


class Field(Base):
    """An agricultural field/parcel: a named polygon with optional crop metadata.

    Kept separate from the generic ``features`` table because fields carry
    first-class agronomic attributes (crop, season), are always auth-gated
    (``features`` GET is intentionally open for the agent), and serve as the
    per-parcel anchor for zonal stats / seasonal time-series.
    """

    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    crop: Mapped[str | None] = mapped_column(String(255), nullable=True)
    season: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
