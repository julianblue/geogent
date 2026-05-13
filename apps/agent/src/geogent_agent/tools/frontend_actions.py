"""Frontend-side action stubs.

These tools exist so the LLM knows the UI exposes four side-effectful actions:
flying the map, drawing a buffer overlay, listing features in the viewport,
and asking the user to confirm a save. The actual work happens in the browser
via assistant-ui's `makeAssistantToolUI` interception — these stubs just return
a structured acknowledgement so the model can continue reasoning.

`confirm_feature_save` uses LangGraph's `interrupt` primitive so the graph
pauses until the user clicks Save or Cancel in the confirmation card.
"""

from typing import Any

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def fly_to(longitude: float, latitude: float, zoom: float | None = None) -> dict:
    """Pan the user's map to the given WGS84 coordinates.

    Use this after `geocode_place` to recenter the map on a city, address, or
    landmark. The browser performs the animation; this tool just records the
    target so the conversation has a record of where the camera went.

    Args:
        longitude: Longitude in WGS84 degrees.
        latitude: Latitude in WGS84 degrees.
        zoom: Optional target zoom level (0-22). Defaults to 12 client-side.
    """
    return {"flown_to": [longitude, latitude], "zoom": zoom if zoom is not None else 12}


@tool
def add_buffer_layer(distance_meters: float, geometry_wkt: str | None = None) -> dict:
    """Draw a buffered geometry as a new overlay on the user's map.

    If `geometry_wkt` is omitted the browser substitutes the current viewport
    bbox. Always call `buffer_geometry` first (the PostGIS-backed tool) if you
    need the resulting WKT in the conversation; this tool only triggers the
    overlay render.

    Args:
        distance_meters: Buffer distance in meters (must be > 0).
        geometry_wkt: Optional input geometry as WKT (SRID 4326). Polygon-shaped.
    """
    return {"queued_overlay": True, "distance_m": distance_meters, "geometry_wkt": geometry_wkt}


@tool
def list_features_in_viewport() -> dict:
    """Ask the UI to render the features currently inside the user's viewport.

    Prefer the server-side `features_within` tool when you need to *read* the
    list yourself for further reasoning. Use this tool when the user wants to
    *see* the list as an interactive card with zoom buttons.
    """
    return {"queued_feature_list": True}


@tool
def confirm_feature_save(name: str, geometry_wkt: str) -> Any:
    """Ask the user to confirm saving a feature to the database.

    Pauses the graph via a LangGraph interrupt; resumes when the UI calls
    `addResult({ ok: true, id })` (Save) or `addResult({ ok: false, cancelled: true })`
    (Cancel). Always prefer this tool over silently writing data.

    Args:
        name: Suggested feature name (user can edit before confirming).
        geometry_wkt: Geometry to persist, as WKT (SRID 4326).
    """
    return interrupt(
        {
            "type": "confirm_feature_save",
            "name": name,
            "geometry_wkt": geometry_wkt,
        }
    )
