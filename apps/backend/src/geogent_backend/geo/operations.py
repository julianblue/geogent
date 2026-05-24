from shapely import wkt as shapely_wkt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class GeometryValidationError(ValueError):
    """Raised when an input WKT is malformed or has the wrong geometry type.

    The FastAPI app maps this to HTTP 400 (see ``geogent_backend.main``).
    """


_POLYGONAL_TYPES = frozenset({"Polygon", "MultiPolygon"})


def _parse_wkt(value: str):
    """Parse WKT with shapely so callers fail fast on malformed input.

    Raises ``GeometryValidationError`` so the FastAPI handler can convert it to
    a 400 response instead of leaking a 500 from PostGIS.
    """
    try:
        return shapely_wkt.loads(value)
    except Exception as exc:
        raise GeometryValidationError(f"Invalid WKT: {exc}") from exc


async def buffer_geometry(session: AsyncSession, wkt: str, distance_m: float) -> str:
    """Buffer a WKT geometry by `distance_m` meters, returning WKT.

    Reprojects 4326 → 3857 for metric buffering, then back to 4326.
    """
    _parse_wkt(wkt)
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


async def distance_between(session: AsyncSession, a_wkt: str, b_wkt: str) -> float:
    """Geodesic distance in meters between two WKT geometries (SRID 4326).

    Uses the geography type so the result is true meters on the WGS84 ellipsoid
    rather than degrees.
    """
    _parse_wkt(a_wkt)
    _parse_wkt(b_wkt)
    sql = text(
        """
        SELECT ST_Distance(
            ST_GeomFromText(:a, 4326)::geography,
            ST_GeomFromText(:b, 4326)::geography
        ) AS distance
        """
    )
    result = await session.execute(sql, {"a": a_wkt, "b": b_wkt})
    return float(result.scalar_one())


async def area_of(session: AsyncSession, wkt: str) -> float:
    """Area of a (multi)polygon WKT in square meters via the geography type.

    Rejects non-polygonal geometries so the caller doesn't silently get 0.0
    back from a Point or LineString.
    """
    geom = _parse_wkt(wkt)
    if geom.geom_type not in _POLYGONAL_TYPES:
        raise GeometryValidationError(
            f"area_of requires a Polygon or MultiPolygon, got {geom.geom_type}"
        )
    sql = text(
        """
        SELECT ST_Area(
            ST_GeomFromText(:wkt, 4326)::geography
        ) AS area
        """
    )
    result = await session.execute(sql, {"wkt": wkt})
    return float(result.scalar_one())


async def geometries_intersect(session: AsyncSession, a_wkt: str, b_wkt: str) -> bool:
    """Whether two WKT geometries (SRID 4326) intersect."""
    _parse_wkt(a_wkt)
    _parse_wkt(b_wkt)
    sql = text(
        """
        SELECT ST_Intersects(
            ST_GeomFromText(:a, 4326),
            ST_GeomFromText(:b, 4326)
        ) AS intersects
        """
    )
    result = await session.execute(sql, {"a": a_wkt, "b": b_wkt})
    return bool(result.scalar_one())


async def fields_in_bbox(
    session: AsyncSession,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[dict]:
    """Fields whose geometry overlaps the given lon/lat bounding box (SRID 4326).

    Uses the ``&&`` bounding-box operator so the GiST index on
    ``fields.geometry`` does the work. Returns one dict per field including the
    geometry as a GeoJSON string (``geojson``) so callers can render it directly.
    """
    if min_lon > max_lon or min_lat > max_lat:
        raise GeometryValidationError(
            "Invalid bbox: expected min_lon <= max_lon and min_lat <= max_lat"
        )
    sql = text(
        """
        SELECT id, name, crop, season, created_at, ST_AsGeoJSON(geometry) AS geojson
        FROM fields
        WHERE geometry && ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
        ORDER BY id
        """
    )
    result = await session.execute(
        sql,
        {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "crop": row.crop,
            "season": row.season,
            "created_at": row.created_at,
            "geojson": row.geojson,
        }
        for row in result
    ]


async def features_within(session: AsyncSession, wkt: str) -> list[dict]:
    """Features whose geometry is fully inside the input WKT (SRID 4326).

    Returns ``[{id, name}, ...]`` ordered by id. Uses the spatial index on
    ``features.geometry``.
    """
    _parse_wkt(wkt)
    sql = text(
        """
        SELECT id, name
        FROM features
        WHERE ST_Within(geometry, ST_GeomFromText(:wkt, 4326))
        ORDER BY id
        """
    )
    result = await session.execute(sql, {"wkt": wkt})
    return [{"id": row.id, "name": row.name} for row in result]
