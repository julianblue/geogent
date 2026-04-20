from sqlalchemy.ext.asyncio import AsyncSession

from geogent_backend.repositories.feature_repo import FeatureRepository
from geogent_backend.schemas.feature import FeatureCreate, FeatureRead


class FeatureService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = FeatureRepository(session)

    async def list_features(self) -> list[FeatureRead]:
        rows = await self._repo.list_all()
        return [FeatureRead.model_validate(r) for r in rows]

    async def create_feature(self, payload: FeatureCreate) -> FeatureRead:
        row = await self._repo.create(payload)
        return FeatureRead.model_validate(row)
