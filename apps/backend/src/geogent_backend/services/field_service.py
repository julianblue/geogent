import json

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.geo.operations import fields_in_bbox
from geogent_backend.models.field import Field
from geogent_backend.repositories.field_repo import FieldRepository
from geogent_backend.schemas.field import FieldCreate, FieldRead, FieldUpdate


def field_to_read(row: Field) -> FieldRead:
    """Build a ``FieldRead`` from an ORM row, converting the WKB geometry to GeoJSON."""
    return FieldRead(
        id=row.id,
        name=row.name,
        crop=row.crop,
        season=row.season,
        geometry=mapping(to_shape(row.geometry)),
        created_at=row.created_at,
    )


class FieldService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = FieldRepository(session)

    async def list_fields(self) -> list[FieldRead]:
        return [field_to_read(r) for r in await self._repo.list_all()]

    async def get_field(self, field_id: int) -> FieldRead | None:
        row = await self._repo.get(field_id)
        return field_to_read(row) if row is not None else None

    async def create_field(self, payload: FieldCreate) -> FieldRead:
        return field_to_read(await self._repo.create(payload))

    async def update_field(self, field_id: int, payload: FieldUpdate) -> FieldRead | None:
        row = await self._repo.get(field_id)
        if row is None:
            return None
        return field_to_read(await self._repo.update(row, payload))

    async def delete_field(self, field_id: int) -> bool:
        row = await self._repo.get(field_id)
        if row is None:
            return False
        await self._repo.delete(row)
        return True

    async def fields_in_bbox(
        self, min_lon: float, min_lat: float, max_lon: float, max_lat: float
    ) -> list[FieldRead]:
        rows = await fields_in_bbox(self._session, min_lon, min_lat, max_lon, max_lat)
        return [
            FieldRead(
                id=r["id"],
                name=r["name"],
                crop=r["crop"],
                season=r["season"],
                geometry=json.loads(r["geojson"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]
