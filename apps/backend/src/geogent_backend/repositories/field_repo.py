from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.models.field import Field
from geogent_backend.schemas.field import FieldCreate, FieldUpdate


class FieldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Field]:
        result = await self._session.execute(select(Field).order_by(Field.id))
        return list(result.scalars().all())

    async def get(self, field_id: int) -> Field | None:
        return await self._session.get(Field, field_id)

    async def create(self, payload: FieldCreate) -> Field:
        geom = shape(payload.geometry.model_dump())
        row = Field(
            name=payload.name,
            crop=payload.crop,
            season=payload.season,
            geometry=from_shape(geom, srid=4326),
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def update(self, row: Field, payload: FieldUpdate) -> Field:
        data = payload.model_dump(exclude_unset=True)
        if "name" in data:
            row.name = data["name"]
        if "crop" in data:
            row.crop = data["crop"]
        if "season" in data:
            row.season = data["season"]
        if data.get("geometry") is not None:
            row.geometry = from_shape(shape(data["geometry"]), srid=4326)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def delete(self, row: Field) -> None:
        await self._session.delete(row)
        await self._session.commit()
