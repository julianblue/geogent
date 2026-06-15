"""Routing, travel-time, isochrone and geocoding endpoints (#55).

Auth-gated thin wrappers over the providers in ``geo/routing.py`` (OSRM,
OpenRouteService, Nominatim). Provider URLs/keys live in settings so the agent
and UI never touch them directly. Upstream failures surface as 502; an
unconfigured isochrone provider surfaces as 503.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from geogent_backend.api.deps import get_current_user
from geogent_backend.geo import routing as routing_provider
from geogent_backend.geo.routing import IsochroneUnavailableError, RoutingError
from geogent_backend.schemas.routing import (
    GeocodeResponse,
    GeocodeResult,
    IsochroneRequest,
    IsochroneResponse,
    MatrixRequest,
    MatrixResponse,
    ReverseGeocodeResponse,
    RouteRequest,
    RouteResponse,
)

# Routing endpoints are not free (they hit external providers); gate them like
# the rest of /api/v1.
router = APIRouter(dependencies=[Depends(get_current_user)])
geocode_router = APIRouter(dependencies=[Depends(get_current_user)])


def _bad_gateway(exc: RoutingError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@router.post("/route", response_model=RouteResponse)
async def route(payload: RouteRequest) -> RouteResponse:
    try:
        result = await routing_provider.route(
            [c.as_tuple() for c in payload.coordinates], payload.profile
        )
    except RoutingError as exc:
        raise _bad_gateway(exc) from exc
    return RouteResponse(profile=payload.profile, **result)


@router.post("/matrix", response_model=MatrixResponse)
async def matrix(payload: MatrixRequest) -> MatrixResponse:
    try:
        result = await routing_provider.matrix(
            [c.as_tuple() for c in payload.coordinates],
            payload.sources,
            payload.destinations,
            payload.profile,
        )
    except RoutingError as exc:
        raise _bad_gateway(exc) from exc
    return MatrixResponse(profile=payload.profile, **result)


@router.post("/isochrone", response_model=IsochroneResponse)
async def isochrone(payload: IsochroneRequest) -> IsochroneResponse:
    try:
        geojson = await routing_provider.isochrone(
            payload.longitude,
            payload.latitude,
            [m * 60 for m in payload.range_minutes],
            payload.profile,
        )
    except IsochroneUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RoutingError as exc:
        raise _bad_gateway(exc) from exc
    return IsochroneResponse(
        profile=payload.profile, range_minutes=payload.range_minutes, geojson=geojson
    )


@geocode_router.get("", response_model=GeocodeResponse)
async def geocode(
    q: str = Query(..., min_length=1, description="Free-form place name or address."),
    limit: int = Query(5, ge=1, le=20),
) -> GeocodeResponse:
    try:
        results = await routing_provider.geocode(q, limit)
    except RoutingError as exc:
        raise _bad_gateway(exc) from exc
    return GeocodeResponse(results=[GeocodeResult(**r) for r in results])


@geocode_router.get("/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
) -> ReverseGeocodeResponse:
    try:
        result = await routing_provider.reverse_geocode(lon, lat)
    except RoutingError as exc:
        raise _bad_gateway(exc) from exc
    return ReverseGeocodeResponse(**result)
