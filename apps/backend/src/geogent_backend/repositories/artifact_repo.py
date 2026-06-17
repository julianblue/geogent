"""Persistence for the artifacts registry (content-addressed heavy datasets)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.models.artifact import Artifact


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, artifact_id: str) -> Artifact | None:
        return await self._session.get(Artifact, artifact_id)

    async def get_by_recipe(self, owner: str | None, recipe_hash: str) -> Artifact | None:
        stmt = select(Artifact).where(
            Artifact.owner.is_(owner) if owner is None else Artifact.owner == owner,
            Artifact.recipe_hash == recipe_hash,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_or_get(
        self,
        artifact_id: str,
        kind: str,
        recipe_hash: str,
        recipe: dict[str, Any],
        owner: str | None,
    ) -> Artifact:
        """Insert a pending artifact, or return the existing row for this
        ``(owner, recipe_hash)``. Idempotent under the unique constraint so two
        racing requests can't both create one (mirrors ``RasterStatCache.put``)."""
        stmt = (
            pg_insert(Artifact)
            .values(
                id=artifact_id,
                kind=kind,
                recipe_hash=recipe_hash,
                status="pending",
                owner=owner,
                recipe=recipe,
            )
            .on_conflict_do_nothing(constraint="uq_artifacts_owner_recipe")
        )
        await self._session.execute(stmt)
        await self._session.commit()
        existing = await self.get_by_recipe(owner, recipe_hash)
        if existing is None:  # pragma: no cover - the row we just inserted must exist
            raise RuntimeError("artifact disappeared after insert")
        return existing

    async def set_status(self, artifact_id: str, status: str) -> None:
        await self._session.execute(
            update(Artifact).where(Artifact.id == artifact_id).values(status=status)
        )
        await self._session.commit()

    async def set_result(
        self, artifact_id: str, summary: dict[str, Any], assets: list[dict[str, Any]]
    ) -> None:
        await self._session.execute(
            update(Artifact)
            .where(Artifact.id == artifact_id)
            .values(status="succeeded", summary=summary, assets=assets, error=None)
        )
        await self._session.commit()

    async def set_error(self, artifact_id: str, error: str) -> None:
        await self._session.execute(
            update(Artifact).where(Artifact.id == artifact_id).values(status="failed", error=error)
        )
        await self._session.commit()
