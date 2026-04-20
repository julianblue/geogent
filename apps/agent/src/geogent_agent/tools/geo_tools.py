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
