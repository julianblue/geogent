import asyncio
import time
from typing import Literal

from langchain_core.tools import tool

from geogent_agent.tools.backend_client import get_backend_client

# Polling cadence for the async time-series job. Kept as module constants (not
# tool args) so the model can't set them.
_TIME_SERIES_POLL_INTERVAL_SECONDS = 0.5
_TIME_SERIES_POLL_TIMEOUT_SECONDS = 60.0


@tool
async def list_features() -> list[dict]:
    """List all stored geospatial features (id, name, properties, geometry)."""
    async with get_backend_client() as client:
        r = await client.get("/api/v1/features")
        r.raise_for_status()
        return r.json()


# With imported parcel datasets (e.g. EuroCrops) the fields table holds
# thousands of rows; cap what a blanket listing feeds back into the context.
_LIST_FIELDS_CAP = 50


@tool
async def list_fields() -> list[dict] | dict:
    """List agricultural fields/parcels available for raster analytics.

    Returns one object per field with its integer ``id``, ``name``, optional
    ``crop``/``season`` metadata, and GeoJSON ``geometry``. Use this to resolve
    the ``field_id`` that ``zonal_stats_for_field`` and
    ``seasonal_index_time_series_for_field`` require when the user names or
    describes a field (e.g. "my north field") rather than selecting one on the
    map. When the user has already clicked a field, prefer
    ``map_state.selected_field.id`` and skip this call.

    Only suitable for small field collections: with a large imported parcel
    dataset the response is truncated and you should use ``fields_within_bbox``
    (spatially scoped, crop-filterable) instead.
    """
    async with get_backend_client() as client:
        r = await client.get("/api/v1/fields")
        r.raise_for_status()
        fields = r.json()
    if len(fields) <= _LIST_FIELDS_CAP:
        return fields
    compact = [
        {k: f.get(k) for k in ("id", "name", "crop", "season")}
        for f in fields[:_LIST_FIELDS_CAP]
    ]
    return {
        "truncated": True,
        "total_fields": len(fields),
        "fields": compact,
        "note": (
            f"showing {_LIST_FIELDS_CAP} of {len(fields)} fields without geometry; "
            "use fields_within_bbox to query by area and crop instead"
        ),
    }


@tool
async def fields_within_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    crop: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Fields/parcels overlapping a lon/lat bounding box, optionally by crop.

    The right way to navigate large imported parcel datasets (e.g. EuroCrops):
    spatially scoped and filterable, unlike ``list_fields``. Defaults the bbox
    naturally to ``map_state.viewport.bounds`` (west, south, east, north) when
    the user asks about "here" / the current view.

    Args:
        min_lon: West edge of the bbox (degrees).
        min_lat: South edge of the bbox (degrees).
        max_lon: East edge of the bbox (degrees).
        max_lat: North edge of the bbox (degrees).
        crop: Case-insensitive crop-name substring, e.g. 'wheat' matches
            'winter_common_soft_wheat'.
        limit: Max parcels to return (default 25).

    Returns compact parcels (id, name, crop, season — no geometry); feed an
    ``id`` into ``zonal_stats_for_field`` / ``seasonal_index_time_series_for_field``.
    """
    params: dict = {
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "limit": limit,
    }
    if crop:
        params["crop"] = crop
    async with get_backend_client() as client:
        r = await client.get("/api/v1/fields/in-bbox", params=params)
        r.raise_for_status()
        fields = r.json()
    return [{k: f.get(k) for k in ("id", "name", "crop", "season")} for f in fields]


@tool
async def crop_stats_within_bbox(
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
) -> list[dict]:
    """Summarize what is grown inside a lon/lat bounding box.

    Returns one row per crop — ``{crop, parcels, total_area_ha}`` — ordered by
    area, so the dominant crop comes first. Prefer this over listing parcels
    when the user asks what is grown in an area, how much of a crop there is,
    or for an area breakdown; defaults the bbox to
    ``map_state.viewport.bounds`` for questions about the current view.
    """
    async with get_backend_client() as client:
        r = await client.get(
            "/api/v1/fields/crop-stats",
            params={
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            },
        )
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


@tool
async def zonal_stats_for_field(
    field_id: int,
    index: Literal["ndvi", "ndwi", "evi"] = "ndvi",
    scene_id: str | None = None,
    datetime: str | None = None,
    max_cloud_cover: float = 20,
    histogram_bins: int = 20,
) -> dict:
    """Compute per-field zonal stats for one raster scene.

    ``index`` must be one of the backend-supported indices: ``ndvi``, ``ndwi``,
    or ``evi``. Request/response field names mirror backend raster schemas for
    #24 widgets.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/analytics/zonal-stats",
            json={
                "field_id": field_id,
                "index": index,
                "scene_id": scene_id,
                "datetime": datetime,
                "max_cloud_cover": max_cloud_cover,
                "histogram_bins": histogram_bins,
            },
        )
        r.raise_for_status()
        return r.json()


@tool
async def seasonal_index_time_series_for_field(
    field_id: int,
    start_date: str,
    end_date: str,
    index: Literal["ndvi", "ndwi", "evi"] = "ndvi",
    max_cloud_cover: float = 20,
    max_scenes: int = 60,
) -> dict:
    """Fetch a field's seasonal index series by starting and polling a backend job.

    ``index`` must be one of the backend-supported indices: ``ndvi``, ``ndwi``,
    or ``evi``. Returns the backend ``TimeSeriesResultResponse`` shape for #24
    chart widgets.
    """
    async with get_backend_client() as client:
        start = await client.post(
            "/api/v1/analytics/time-series",
            json={
                "field_id": field_id,
                "index": index,
                "start_date": start_date,
                "end_date": end_date,
                "max_cloud_cover": max_cloud_cover,
                "max_scenes": max_scenes,
            },
        )
        start.raise_for_status()
        job = start.json()
        job_id = job["job_id"]
        deadline = time.monotonic() + _TIME_SERIES_POLL_TIMEOUT_SECONDS

        while True:
            status_resp = await client.get(f"/api/v1/analytics/time-series/{job_id}")
            status_resp.raise_for_status()
            result = status_resp.json()
            status = result.get("status")
            if status == "succeeded":
                return result
            if status == "failed":
                error = result.get("error") or f"time-series job {job_id} failed"
                raise RuntimeError(str(error))
            if time.monotonic() >= deadline:
                raise TimeoutError(f"time-series job {job_id} did not finish before timeout")
            await asyncio.sleep(_TIME_SERIES_POLL_INTERVAL_SECONDS)
