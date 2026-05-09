from langchain_core.tools import tool

from geogent_agent.tools.backend_client import get_backend_client


@tool
async def list_features() -> list[dict]:
    """List all stored geospatial features (id, name, properties, geometry)."""
    async with get_backend_client() as client:
        r = await client.get("/api/v1/features")
        r.raise_for_status()
        return r.json()


@tool
async def buffer_geometry(geometry_wkt: str, distance_m: float) -> str:
    """Buffer a WKT geometry by `distance_m` meters via PostGIS. Returns WKT.

    Args:
        geometry_wkt: Input geometry as WKT, e.g. 'POINT(-122.42 37.77)'.
        distance_m: Buffer distance in meters (positive).
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/analytics/buffer",
            json={"geometry_wkt": geometry_wkt, "distance_m": distance_m},
        )
        r.raise_for_status()
        return r.json()["buffered_wkt"]


@tool
async def distance_between(a_wkt: str, b_wkt: str) -> float:
    """Geodesic distance in meters between two WKT geometries (SRID 4326).

    Args:
        a_wkt: First geometry as WKT, e.g. 'POINT(-122.42 37.77)'.
        b_wkt: Second geometry as WKT, e.g. 'POINT(-73.98 40.75)'.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/analytics/distance",
            json={"a_wkt": a_wkt, "b_wkt": b_wkt},
        )
        r.raise_for_status()
        return r.json()["distance_m"]


@tool
async def area_of(geometry_wkt: str) -> float:
    """Area of a (multi)polygon WKT in square meters (SRID 4326).

    Args:
        geometry_wkt: Polygon or multipolygon as WKT.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/analytics/area",
            json={"geometry_wkt": geometry_wkt},
        )
        r.raise_for_status()
        return r.json()["area_m2"]


@tool
async def geometries_intersect(a_wkt: str, b_wkt: str) -> bool:
    """Whether two WKT geometries (SRID 4326) intersect.

    Args:
        a_wkt: First geometry as WKT.
        b_wkt: Second geometry as WKT.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/analytics/intersects",
            json={"a_wkt": a_wkt, "b_wkt": b_wkt},
        )
        r.raise_for_status()
        return r.json()["intersects"]


@tool
async def features_within(geometry_wkt: str) -> list[dict]:
    """Features whose geometry is fully inside the given WKT search area.

    Returns a list of ``{id, name}`` references; use ``list_features`` for full
    geometries and properties.

    Args:
        geometry_wkt: Search area as WKT (SRID 4326), typically a polygon.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/analytics/features-within",
            json={"geometry_wkt": geometry_wkt},
        )
        r.raise_for_status()
        return r.json()["features"]
