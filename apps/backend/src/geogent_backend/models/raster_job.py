from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geogent_backend.db.base import Base


class RasterJob(Base):
    """A background seasonal time-series job over a field.

    ``params`` captures the request (index, date range, cloud filter) and
    ``result`` holds the computed points once the job succeeds. ``id`` is a
    uuid4 hex string set by the service.
    """

    __tablename__ = "raster_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    field_id: Mapped[int] = mapped_column(Integer, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RasterStatCache(Base):
    """Immutable per-(scene, polygon, index, bins) zonal-stats result cache.

    A scene + polygon never change, so results are cached aggressively keyed by
    a sha256 digest. Shared by both the zonal-stats and time-series paths.
    """

    __tablename__ = "raster_stat_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    histogram: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
