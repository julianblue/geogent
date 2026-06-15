"""Routing, travel-time, isochrone and reverse-geocoding tools (#55).

Thin stateless wrappers over the auth-gated backend ``/api/v1/routing/*`` and
``/api/v1/geocode/*`` endpoints — the same pattern as ``geo_tools.py``. Forward
geocoding (place name → coordinates) stays in ``geocode_place``; resolve names
with it first, then feed the coordinates to ``route_between`` / ``isochrone_for``.
"""

from typing import Literal

from langchain_core.tools import tool

from geogent_agent.tools.backend_client import get_backend_client

Profile = Literal["driving", "walking", "cycling"]


@tool
async def route_between(
    origin_lon: float,
    origin_lat: float,
    dest_lon: float,
    dest_lat: float,
    profile: Profile = "driving",
) -> dict:
    """Compute a route between two WGS84 points and return its summary.

    Geocode place names with ``geocode_place`` first, then pass coordinates here.
    Returns ``{distance_km, duration_min, profile, geometry}`` where ``geometry``
    is a GeoJSON ``LineString``. To DRAW the route on the user's map, also call
    the ``add_route_layer`` UI tool.

    Args:
        origin_lon: Origin longitude (degrees).
        origin_lat: Origin latitude (degrees).
        dest_lon: Destination longitude (degrees).
        dest_lat: Destination latitude (degrees).
        profile: Travel mode — ``driving`` (default), ``walking``, or ``cycling``.
            The default OSRM provider only serves ``driving``.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/routing/route",
            json={
                "coordinates": [
                    {"longitude": origin_lon, "latitude": origin_lat},
                    {"longitude": dest_lon, "latitude": dest_lat},
                ],
                "profile": profile,
            },
        )
        r.raise_for_status()
        data = r.json()
    return {
        "distance_km": round(data["distance_m"] / 1000, 2),
        "duration_min": round(data["duration_s"] / 60, 1),
        "profile": data["profile"],
        "geometry": data["geometry"],
    }


@tool
async def travel_time_matrix(
    points: list[list[float]],
    profile: Profile = "driving",
) -> dict:
    """Travel-time + distance matrix between a set of WGS84 points.

    ``points`` is a list of ``[longitude, latitude]`` pairs (geocode names with
    ``geocode_place`` first). Returns ``{durations_min, distances_km}`` as
    row-major matrices (entry [i][j] = i→j); ``null`` marks an unreachable pair.

    Args:
        points: List of ``[lon, lat]`` pairs (at least two).
        profile: Travel mode — ``driving`` (default), ``walking``, or ``cycling``.
    """
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/routing/matrix",
            json={
                "coordinates": [{"longitude": p[0], "latitude": p[1]} for p in points],
                "profile": profile,
            },
        )
        r.raise_for_status()
        data = r.json()

    def _scale(grid: list[list[float | None]] | None, factor: float) -> list[list[float | None]]:
        if not grid:
            return []
        return [[round(v * factor, 2) if v is not None else None for v in row] for row in grid]

    return {
        "durations_min": _scale(data.get("durations_s"), 1 / 60),
        "distances_km": _scale(data.get("distances_m"), 1 / 1000),
        "profile": data["profile"],
    }


@tool
async def isochrone_for(
    longitude: float,
    latitude: float,
    range_minutes: list[float] | None = None,
    profile: Profile = "driving",
) -> dict:
    """Reachability area(s) around a point — "what's within N minutes".

    Returns ``{range_minutes, profile, geojson}`` where ``geojson`` is a GeoJSON
    ``FeatureCollection`` of reachability polygons. To DRAW them on the user's
    map, also call the ``add_isochrone_layer`` UI tool. Requires an
    OpenRouteService key on the backend; without one the tool errors clearly.

    Args:
        longitude: Center longitude (degrees).
        latitude: Center latitude (degrees).
        range_minutes: Time budgets in minutes (default ``[10]``), e.g.
            ``[5, 10, 15]``.
        profile: Travel mode — ``driving`` (default), ``walking``, or ``cycling``.
    """
    ranges = range_minutes or [10]
    async with get_backend_client() as client:
        r = await client.post(
            "/api/v1/routing/isochrone",
            json={
                "longitude": longitude,
                "latitude": latitude,
                "range_minutes": ranges,
                "profile": profile,
            },
        )
        r.raise_for_status()
        return r.json()


@tool
async def reverse_geocode(longitude: float, latitude: float) -> dict:
    """Resolve a WGS84 point to the nearest address/place via the backend.

    Returns ``{display_name, longitude, latitude, type, address}``. Use this to
    answer "what's here / what's at these coordinates". For the opposite
    direction (place name → coordinates) use ``geocode_place``.

    Args:
        longitude: Longitude in WGS84 degrees.
        latitude: Latitude in WGS84 degrees.
    """
    async with get_backend_client() as client:
        r = await client.get(
            "/api/v1/geocode/reverse",
            params={"lon": longitude, "lat": latitude},
        )
        r.raise_for_status()
        return r.json()
