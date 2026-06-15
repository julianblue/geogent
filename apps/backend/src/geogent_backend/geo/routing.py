"""Routing, travel-time, isochrone and geocoding providers (#55).

Thin ``httpx`` wrappers over pluggable, self-hostable backends — the same
pattern as ``geo/stac.py``. Keeping the provider calls here lets the API routes
stay declarative and keeps provider URLs/keys server-side:

- **OSRM** for point-to-point routing (``/route``) and the duration/distance
  matrix (``/table``). The public demo (``router.project-osrm.org``) only serves
  the ``driving`` profile; a self-hosted OSRM can serve walking/cycling.
- **OpenRouteService** for isochrones — OSRM has no native isochrone, so this is
  a separate provider and requires ``ORS_API_KEY`` (or a keyless self-host).
- **Nominatim** for forward + reverse geocoding.

All callers must validate coordinates before reaching the provider; the helpers
here only format and dispatch, then normalise the response shape.
"""

from __future__ import annotations

from typing import Literal

import httpx

from geogent_backend.config import get_settings

Profile = Literal["driving", "walking", "cycling"]

# OSRM serves profiles as a path segment; ORS uses a different vocabulary.
_OSRM_PROFILE = {"driving": "driving", "walking": "walking", "cycling": "cycling"}
_ORS_PROFILE = {
    "driving": "driving-car",
    "walking": "foot-walking",
    "cycling": "cycling-regular",
}

# The hosted OpenRouteService API requires a key; a self-hosted instance
# (any other base URL) may be keyless. Used to decide whether to 503.
_PUBLIC_ORS_HOST = "api.openrouteservice.org"


class RoutingError(Exception):
    """A routing/geocoding provider request failed or returned no result."""


class IsochroneUnavailableError(RoutingError):
    """Isochrones are requested but no provider/key is configured."""


def _coords_param(coordinates: list[tuple[float, float]]) -> str:
    """OSRM-style ``lon,lat;lon,lat`` string. Inputs are floats, so no path
    separators or traversal sequences can be smuggled into the URL."""
    return ";".join(f"{lon},{lat}" for lon, lat in coordinates)


async def route(
    coordinates: list[tuple[float, float]],
    profile: Profile = "driving",
) -> dict:
    """Route through ``coordinates`` (lon, lat) in order via OSRM.

    Returns ``{distance_m, duration_s, geometry}`` where ``geometry`` is a
    GeoJSON ``LineString`` (simplified overview). Raises :class:`RoutingError`
    if no route is found.
    """
    settings = get_settings()
    base = settings.osrm_base_url.rstrip("/")
    osrm_profile = _OSRM_PROFILE[profile]
    path = f"/route/v1/{osrm_profile}/{_coords_param(coordinates)}"
    async with httpx.AsyncClient(timeout=settings.routing_timeout_seconds) as client:
        resp = await client.get(
            f"{base}{path}",
            params={"overview": "simplified", "geometries": "geojson", "steps": "false"},
        )
    if resp.status_code >= 400:
        raise RoutingError(f"OSRM route request failed ({resp.status_code}).")
    body = resp.json()
    routes = body.get("routes") or []
    if body.get("code") != "Ok" or not routes:
        raise RoutingError("No route found between the given points.")
    top = routes[0]
    return {
        "distance_m": float(top["distance"]),
        "duration_s": float(top["duration"]),
        "geometry": top["geometry"],
    }


async def matrix(
    coordinates: list[tuple[float, float]],
    sources: list[int] | None,
    destinations: list[int] | None,
    profile: Profile = "driving",
) -> dict:
    """Duration + distance matrix between ``coordinates`` via OSRM ``/table``.

    ``sources``/``destinations`` are indices into ``coordinates``; ``None`` means
    "all points". Returns ``{durations_s, distances_m}`` as row-major matrices.
    """
    settings = get_settings()
    base = settings.osrm_base_url.rstrip("/")
    osrm_profile = _OSRM_PROFILE[profile]
    path = f"/table/v1/{osrm_profile}/{_coords_param(coordinates)}"
    params: dict = {"annotations": "duration,distance"}
    if sources is not None:
        params["sources"] = ";".join(str(i) for i in sources)
    if destinations is not None:
        params["destinations"] = ";".join(str(i) for i in destinations)
    async with httpx.AsyncClient(timeout=settings.routing_timeout_seconds) as client:
        resp = await client.get(f"{base}{path}", params=params)
    if resp.status_code >= 400:
        raise RoutingError(f"OSRM table request failed ({resp.status_code}).")
    body = resp.json()
    if body.get("code") != "Ok":
        raise RoutingError("Travel-time matrix could not be computed.")
    return {
        "durations_s": body.get("durations"),
        "distances_m": body.get("distances"),
    }


async def isochrone(
    longitude: float,
    latitude: float,
    range_seconds: list[float],
    profile: Profile = "driving",
) -> dict:
    """Reachability polygons around a point via OpenRouteService.

    Returns a GeoJSON ``FeatureCollection`` (one feature per range, largest
    first per the ORS contract). Raises :class:`IsochroneUnavailableError` when no
    ORS key is configured.
    """
    settings = get_settings()
    base = settings.ors_base_url.rstrip("/")
    # The hosted ORS API needs a key; a self-hosted base URL may be keyless.
    if not settings.ors_api_key and _PUBLIC_ORS_HOST in base:
        raise IsochroneUnavailableError(
            "Isochrones require an OpenRouteService key. Set ORS_API_KEY "
            "(or point ORS_BASE_URL at a keyless self-hosted instance)."
        )
    ors_profile = _ORS_PROFILE[profile]
    headers = {"Accept": "application/json"}
    if settings.ors_api_key:
        headers["Authorization"] = settings.ors_api_key
    async with httpx.AsyncClient(timeout=settings.routing_timeout_seconds) as client:
        resp = await client.post(
            f"{base}/v2/isochrones/{ors_profile}",
            headers=headers,
            json={
                "locations": [[longitude, latitude]],
                "range": range_seconds,
                "range_type": "time",
            },
        )
    if resp.status_code >= 400:
        raise RoutingError(f"OpenRouteService isochrone request failed ({resp.status_code}).")
    return resp.json()


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=settings.nominatim_base_url.rstrip("/"),
        timeout=settings.routing_timeout_seconds,
        headers={"User-Agent": settings.geocoder_user_agent, "Accept": "application/json"},
    )


def _to_bbox(raw: object) -> list[float] | None:
    # Nominatim returns boundingbox as [south, north, west, east] strings;
    # normalise to [west, south, east, north] floats.
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        south, north, west, east = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    return [west, south, east, north]


async def geocode(query: str, limit: int = 5) -> list[dict]:
    """Forward-geocode ``query`` via Nominatim → ranked candidates."""
    async with _client() as client:
        resp = await client.get(
            "/search",
            params={"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 0},
        )
    if resp.status_code >= 400:
        raise RoutingError(f"Geocode request failed ({resp.status_code}).")
    return [
        {
            "display_name": hit.get("display_name", ""),
            "longitude": float(hit["lon"]),
            "latitude": float(hit["lat"]),
            "type": hit.get("type"),
            "bbox": _to_bbox(hit.get("boundingbox")),
        }
        for hit in resp.json()
    ]


async def reverse_geocode(longitude: float, latitude: float) -> dict:
    """Reverse-geocode a point via Nominatim → nearest address/place."""
    async with _client() as client:
        resp = await client.get(
            "/reverse",
            params={"lon": longitude, "lat": latitude, "format": "jsonv2"},
        )
    if resp.status_code >= 400:
        raise RoutingError(f"Reverse-geocode request failed ({resp.status_code}).")
    body = resp.json()
    if body.get("error"):
        raise RoutingError("No address found for the given point.")
    return {
        "display_name": body.get("display_name", ""),
        "longitude": float(body.get("lon", longitude)),
        "latitude": float(body.get("lat", latitude)),
        "type": body.get("type"),
        "address": body.get("address") or {},
    }
