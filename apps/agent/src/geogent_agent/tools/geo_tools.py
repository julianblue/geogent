import asyncio
import time
from typing import Literal

from langchain_core.tools import tool

from geogent_agent.tools.backend_client import get_backend_client

# Polling cadence for the async time-series job. Kept as module constants (not
# tool args) so the model can't set them.
_TIME_SERIES_POLL_INTERVAL_SECONDS = 0.5
_TIME_SERIES_POLL_TIMEOUT_SECONDS = 60.0

# The cube/field-memory build reads many scenes, so it gets a longer budget than
# the per-scene time-series job. Also module constants, not tool args.
_ARTIFACT_POLL_INTERVAL_SECONDS = 0.5
_ARTIFACT_POLL_TIMEOUT_SECONDS = 180.0

# Season analysis can read several years of scenes in one job (one window per
# baseline year), so it gets the longest budget of the three.
_SEASON_ANALYSIS_POLL_INTERVAL_SECONDS = 0.5
_SEASON_ANALYSIS_POLL_TIMEOUT_SECONDS = 300.0


def _resolve_aoi(
    *,
    field_id: int | None,
    geometry_wkt: str | None,
    bbox: list[float] | None,
) -> dict:
    """Normalize the three AOI forms into the recipe's single-AOI payload.

    The backend enforces "exactly one of field_id / geometry_wkt / bbox" and
    answers a violation with a 422. Checking here instead turns a model mistake
    into a message it can actually act on (and keeps a half-specified request
    from being sent as ``field_id: null``, which reads as a server error).
    """
    provided = {
        "field_id": field_id,
        "geometry_wkt": geometry_wkt,
        "bbox": bbox,
    }
    given = {k: v for k, v in provided.items() if v is not None}
    if len(given) != 1:
        raise ValueError(
            "Pass exactly one area of interest: field_id (a stored field), "
            "geometry_wkt (a WGS84 polygon), or bbox "
            f"[min_lon, min_lat, max_lon, max_lat]. Got: {sorted(given) or 'none'}."
        )
    if bbox is not None and len(bbox) != 4:
        raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat] (4 numbers).")
    return given


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
        {k: f.get(k) for k in ("id", "name", "crop", "season")} for f in fields[:_LIST_FIELDS_CAP]
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
    """Features whose geometry is fully inside the given WKT search area —
    returned TO YOU, so you can name, count, or reason about them in chat.

    This is the right tool whenever the user asks what features are in an
    area / the current view: build the WKT polygon from the viewport bounds.
    (`list_features_in_viewport` is display-only and returns no data.) Returns
    a list of ``{id, name}`` references; use ``list_features`` for full
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
    index: Literal["ndvi", "ndwi", "evi", "nbr", "ndmi", "mndwi", "ndre", "savi"] = "ndvi",
    scene_id: str | None = None,
    datetime: str | None = None,
    max_cloud_cover: float = 20,
    histogram_bins: int = 20,
) -> dict:
    """Compute per-field zonal stats (mean/min/max/std + histogram) for one scene.

    The single-date view of a field: "how does it look right now". Cloud and
    shadow pixels are masked out server-side, so the stats describe usable
    ground, and ``stats.valid_pixels`` tells you how much of the field survived
    the mask — a low count means a cloudy scene, not a bad field.

    Indices (pick for the question, not by habit):
      - ``ndvi`` — general vegetation vigour / biomass. The default.
      - ``evi`` — like NDVI but resists saturation on dense canopy.
      - ``savi`` — soil-adjusted; better on sparse/early-season canopy.
      - ``ndre`` — red-edge; nitrogen/chlorophyll status in closed canopy
        (Sentinel-2 only, Landsat has no red-edge band).
      - ``ndmi`` — canopy moisture (drought/irrigation stress).
      - ``nbr`` — burn severity / severe senescence.
      - ``ndwi`` / ``mndwi`` — open water (ponding, flooding).

    Omit ``scene_id`` to use the latest scene under ``max_cloud_cover``; pass
    ``datetime`` (STAC instant or interval) to pin a date window instead.
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
    index: Literal["ndvi", "ndwi", "evi", "nbr", "ndmi", "mndwi", "ndre", "savi"] = "ndvi",
    max_cloud_cover: float = 20,
    max_scenes: int = 60,
) -> dict:
    """Fetch a field's per-scene index series over a date range (raw points).

    One point per usable scene: ``mean``/``min``/``max``/``std`` of the index
    inside the field polygon, cloud-masked. Use this when the user wants the
    actual observations or a chart of them.

    Interpret the shape, don't just relay it: green-up, peak, senescence, and
    any mid-season dip are the agronomic content of a series.

    ``index`` accepts the same set as ``zonal_stats_for_field``.
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


@tool
async def temporal_features(
    start_date: str,
    end_date: str,
    field_id: int | None = None,
    geometry_wkt: str | None = None,
    bbox: list[float] | None = None,
    index: Literal["ndvi", "ndwi", "evi", "nbr", "ndmi", "mndwi", "ndre", "savi"] = "ndvi",
    reducer: Literal["field_memory", "composite", "trend", "frequency"] = "field_memory",
    collection: Literal["sentinel-2-l2a", "landsat-c2-l2"] = "sentinel-2-l2a",
    threshold: float | None = None,
    max_cloud_cover: float = 20,
    max_scenes: int = 60,
) -> dict:
    """Build a multi-date data cube over an area and reduce it PER PIXEL.

    This is the "where inside this field, and how has it behaved over time"
    tool — the within-field view that zonal stats (one number per field) and
    the seasonal series (one number per date) both average away.

    AOI — pass EXACTLY ONE of:
      - ``field_id`` — a stored field/parcel (preferred; use the id from
        ``map_state.selected_field`` or ``fields_within_bbox``),
      - ``geometry_wkt`` — an arbitrary polygon in WGS84 (e.g. a drawn AOI),
      - ``bbox`` — ``[min_lon, min_lat, max_lon, max_lat]``.
    The engine is field/farm-scale: oversized AOIs are rejected (422), so keep
    an area within a few km across.

    Reducers — each writes the named per-pixel layers into ``summary.outputs``:
      - ``field_memory`` (default) → ``productivity`` (multi-date mean) and
        ``stability`` (temporal CV). "Consistently good vs erratic" — the
        management-zone view, and the input to ``delineate_management_zones``.
      - ``composite`` → ``composite``: median index, a typical cloud-free value.
      - ``trend`` → ``slope``: change per year (greening / browning / decline).
      - ``frequency`` → ``frequency``: fraction of dates above ``threshold``
        (waterlogging, bare-soil frequency, cover persistence). Set ``threshold``.

    Give it a long enough window to be meaningful: one full season for
    ``field_memory``/``composite``, several seasons for ``trend``.

    Returns ``{artifact_id, status, summary, ...}``. Read
    ``summary.outputs[<name>].within_field_spread`` first: near-zero means the
    field is uniform and there is nothing worth zoning; larger means real
    structure. Also check ``summary.valid_obs`` — few valid observations per
    pixel (a cloudy season) makes the layers noisy, and you should say so.
    Then call ``show_temporal_layer(artifact_id, band=<output name>)`` to put it
    on the map. The pixels themselves are never returned to you.
    """
    reducer_params = {"threshold": threshold} if threshold is not None else {}
    aoi = _resolve_aoi(field_id=field_id, geometry_wkt=geometry_wkt, bbox=bbox)
    async with get_backend_client() as client:
        start = await client.post(
            "/api/v1/analytics/temporal-features",
            json={
                **aoi,
                "index": index,
                "reducer": reducer,
                "collection": collection,
                "reducer_params": reducer_params,
                "start_date": start_date,
                "end_date": end_date,
                "max_cloud_cover": max_cloud_cover,
                "max_scenes": max_scenes,
            },
        )
        start.raise_for_status()
        artifact_id = start.json()["artifact_id"]
        deadline = time.monotonic() + _ARTIFACT_POLL_TIMEOUT_SECONDS

        while True:
            status_resp = await client.get(f"/api/v1/analytics/artifacts/{artifact_id}")
            status_resp.raise_for_status()
            result = status_resp.json()
            status = result.get("status")
            if status == "succeeded":
                return result
            if status == "failed":
                error = result.get("error") or f"temporal-features build {artifact_id} failed"
                raise RuntimeError(str(error))
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"temporal-features build {artifact_id} did not finish before timeout"
                )
            await asyncio.sleep(_ARTIFACT_POLL_INTERVAL_SECONDS)


@tool
async def analyze_index_season(
    field_id: int,
    start_date: str,
    end_date: str,
    index: Literal["ndvi", "ndwi", "evi", "nbr", "ndmi", "mndwi", "ndre", "savi"] = "ndvi",
    baseline_years: int = 0,
    max_cloud_cover: float = 20,
    max_scenes: int = 60,
) -> dict:
    """Interpret a field's season: phenology metrics, and how it compares to past years.

    This is the analytical step above ``seasonal_index_time_series_for_field``.
    That tool hands you raw per-scene means; this one fits the season's shape and
    returns the numbers an agronomist actually reads:

    - ``phenology``: ``start_of_season``, ``peak_date`` / ``peak_value``,
      ``end_of_season``, ``season_length_days``, ``amplitude``,
      ``seasonal_integral`` (cumulative canopy — the best single proxy for
      biomass, far better than peak alone), ``greenup_rate_per_day`` and
      ``senescence_rate_per_day``.
    - ``anomaly`` (only when ``baseline_years`` > 0): the same window pulled from
      each of the N previous years and compared day-by-day —
      ``mean_difference``, ``mean_z_score``,
      ``fraction_of_season_below_baseline``, and the dates of the largest
      shortfall and surplus. This is how you answer "is this year bad, or does
      this field always look like this?".
    - ``curve``: the smoothed daily curve, downsampled — pass it to
      ``render_dashboard`` as a timeseries panel.
    - ``points``: the underlying per-scene observations.

    Use it for: "how is the season going", "when did it green up", "is it
    behind", "how does this compare to last year", "did the crop mature early".

    Choose the window to cover the whole season, including bare soil at both
    ends — the metrics are defined against that baseline. For a winter crop,
    that means starting the previous autumn; baseline years are aligned by
    position in the window, not calendar date, so winter seasons compare
    correctly.

    ``baseline_years`` multiplies the imagery read (and the wait), so use 0 when
    the user only asks about this season, 2-3 for a comparison. Capped at 5.

    Check ``phenology.status`` first: ``insufficient_data`` means too few clear
    scenes to read a shape, and ``max_gap_days`` tells you whether the curve
    spans a long cloudy hole. Say so rather than reporting metrics as solid.
    """
    async with get_backend_client() as client:
        start = await client.post(
            "/api/v1/analytics/season-analysis",
            json={
                "field_id": field_id,
                "index": index,
                "start_date": start_date,
                "end_date": end_date,
                "baseline_years": baseline_years,
                "max_cloud_cover": max_cloud_cover,
                "max_scenes": max_scenes,
            },
        )
        start.raise_for_status()
        job_id = start.json()["job_id"]
        deadline = time.monotonic() + _SEASON_ANALYSIS_POLL_TIMEOUT_SECONDS

        while True:
            poll = await client.get(f"/api/v1/analytics/season-analysis/{job_id}")
            poll.raise_for_status()
            result = poll.json()
            status = result.get("status")
            if status == "succeeded":
                return result
            if status == "failed":
                error = result.get("error") or f"season-analysis job {job_id} failed"
                raise RuntimeError(str(error))
            if time.monotonic() >= deadline:
                raise TimeoutError(f"season-analysis job {job_id} did not finish before timeout")
            await asyncio.sleep(_SEASON_ANALYSIS_POLL_INTERVAL_SECONDS)
