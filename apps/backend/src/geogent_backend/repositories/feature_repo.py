from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.models.feature import Feature
from geogent_backend.schemas.feature import FeatureCreate


class FeatureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Feature]:
        result = await self._session.execute(select(Feature).order_by(Feature.id))
        return list(result.scalars().all())

    async def create(self, payload: FeatureCreate) -> Feature:
        geom = shape(payload.geometry.model_dump())
        row = Feature(
            name=payload.name,
            properties=payload.properties,
            geometry=from_shape(geom, srid=4326),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row
