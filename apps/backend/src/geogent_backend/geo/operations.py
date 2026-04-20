from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def buffer_geometry(session: AsyncSession, wkt: str, distance_m: float) -> str:
    """Buffer a WKT geometry by `distance_m` meters, returning WKT.

    Reprojects 4326 → 3857 for metric buffering, then back to 4326.
    """
    sql = text(
        """
        SELECT ST_AsText(
            ST_Transform(
                ST_Buffer(
                    ST_Transform(ST_GeomFromText(:wkt, 4326), 3857),
                    :distance
                ),
                4326
            )
        ) AS buffered
        """
    )
    result = await session.execute(sql, {"wkt": wkt, "distance": distance_m})
    return result.scalar_one()
