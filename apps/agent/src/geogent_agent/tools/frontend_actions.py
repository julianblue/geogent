"""Frontend-side tool definitions.

These tools tell the LLM what side effects the UI can perform. They span two
mechanisms handled in the browser under `components/assistant/tools/` and the
interrupt-card widget layer under `components/copilot/cards/` (renamed in #16):

1. Client tools (assistant-ui's `useAssistantTool`). The browser executes the
   action and the tool just returns a structured acknowledgement so the model
   can keep reasoning. These include `add_buffer_layer` and
   `list_features_in_viewport` (plus `fly_to` for map camera movement).

2. LangGraph `interrupt()` tools. The graph pauses until the user acts in the
   UI, which then resumes it with a result. These are `show_sentinel2_scene`
   (the UI renders the scene and resumes) and `confirm_feature_save` (the user
   clicks Save or Cancel in the confirmation card).
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
def show_sentinel2_scene(
    item_id: str | None = None,
    bbox: list[float] | None = None,
    composite: str = "true-color",
) -> Any:
    """Render a Sentinel-2 L2A scene on the user's map.

    The browser handles the actual COG fetch + GPU compositing via deck.gl —
    this tool emits a LangGraph interrupt that the UI executes, then resumes
    the graph with `{ok, item_id, datetime, cloud_cover}` so the agent knows
    what got rendered.

    Pass either ``item_id`` (preferred — from a prior ``stac_search`` you ran
    with the right sortby + cloud filter) or a ``bbox`` (the UI will pick the
    latest cloud-free scene intersecting it automatically). If both are passed,
    ``item_id`` wins.

    Args:
        item_id: A Sentinel-2 L2A item id (e.g. ``"S2B_31UGS_20260501_0_L2A"``).
        bbox: ``[west, south, east, north]`` in WGS84 degrees. Used when the
            caller hasn't already resolved an item id.
        composite: Visualization preset. Defaults to ``"true-color"``.

            RGB composites (natural / false-color blends of three bands):
              - ``"true-color"``        red/green/blue, what the eye sees.
              - ``"false-color-ir"``    nir/red/green, vegetation = bright red.
              - ``"agriculture"``       swir16/nir/blue, crop vigour & soil.
              - ``"burned-area"``       swir22/swir16/nir, recent fire scars.

            Indices (GPU-computed band math with an inline colormap):
              - ``"ndvi"``  vegetation health/density — brown→yellow→green.
              - ``"ndwi"``  surface water / wetlands — tan→light→deep blue.
              - ``"nbr"``   burn severity — dark→orange→green.
              - ``"evi"``   dense-canopy biomass — pale→lime→dark green.

            Pick by user intent: "vegetation/crops/health" → ndvi, "water/lakes/
            rivers/floods" → ndwi, "fire/burn/wildfire" → nbr or burned-area,
            "biomass/forest density" → evi. Default to true-color when unsure.
    """
    return interrupt(
        {
            "type": "show_sentinel2_scene",
            "item_id": item_id,
            "bbox": bbox,
            "composite": composite,
        }
    )


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
