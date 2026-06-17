from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geogent_backend.db.base import Base


class Artifact(Base):
    """A materialized heavy dataset (cube / temporal-feature layer / zone map).

    Generalizes the two patterns in ``raster_job.py``: a job lifecycle
    (``status`` / ``error``) plus a content-addressed cache (``recipe_hash``),
    with the heavy payload kept *out* of the row — ``assets`` holds storage
    URIs, not bytes. ``id`` is a uuid4 hex string used as the stable handle the
    agent passes around; ``recipe_hash`` is the dedup key. Only ``summary`` is
    ever returned to the agent; ``assets`` are resolved to render URLs for the
    UI. See ADR 0002 and docs/design/m1-artifacts-data-model.md.
    """

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    recipe_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Non-NULL ("" = unowned) so UNIQUE(owner, recipe_hash) actually dedups:
    # Postgres treats NULLs as distinct, which would defeat content-addressing.
    owner: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")

    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    assets: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # Content-addressing scoped per owner: one user's cached cube can't be
        # probed or served to another (fail-closed, #50).
        UniqueConstraint("owner", "recipe_hash", name="uq_artifacts_owner_recipe"),
        Index("ix_artifacts_status", "status"),
    )
