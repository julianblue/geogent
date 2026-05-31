"""Frontend-side tool definitions.

These tools tell the LLM what side effects the UI can perform. They span two
mechanisms handled in the browser under `components/assistant/tools/`:

1. Client tools (assistant-ui's `useAssistantTool`). The browser executes the
   action and the tool just returns a structured acknowledgement so the model
   can keep reasoning. These are `fly_to`, `add_buffer_layer`, and
   `list_features_in_viewport`.

2. LangGraph `interrupt()` tools. The graph pauses until the user acts in the
   UI, which then resumes it with a result. These are `show_sentinel2_scene`
   (the UI renders the scene and resumes) and `confirm_feature_save` (the user
   clicks Save or Cancel in the confirmation card).
"""

from typing import Annotated, Any, Literal

from langchain_core.tools import tool
from langgraph.types import interrupt
from pydantic import BaseModel, Field


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
    field_id: int | None = None,
    bbox: list[float] | None = None,
    composite: str = "true-color",
) -> Any:
    """Render a Sentinel-2 L2A scene on the user's map.

    The browser handles the actual COG fetch + GPU compositing via deck.gl —
    this tool emits a LangGraph interrupt that the UI executes, then resumes
    the graph with `{ok, item_id, datetime, cloud_cover}` so the agent knows
    what got rendered.

    Pass either ``item_id`` (preferred — from a prior ``stac_search`` you ran
    with the right sortby + cloud filter), ``field_id`` (for parcel-scoped ag
    workflows), or a ``bbox`` (the UI will pick the latest cloud-free scene
    intersecting it automatically). If multiple targets are passed, ``item_id``
    wins, then ``field_id``, then ``bbox``.

    #24 UI note: this interrupt payload is consumed by upcoming agriculture
    widgets, so keep field identifiers and index-composite intent explicit.

    Args:
        item_id: A Sentinel-2 L2A item id (e.g. ``"S2B_31UGS_20260501_0_L2A"``).
        field_id: Field id to target when the user asks for a parcel/field.
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
            "field_id": field_id,
            "bbox": bbox,
            "composite": composite,
        }
    )


# --- render_dashboard: LLM-composed dashboard spec (ADR 0001, tier 2) ---------
#
# The agent assembles several panels into a vetted layout; the browser validates
# this spec (mirrored as a Zod schema in
# apps/ui/src/components/assistant/widgets/dashboard/schema.ts) and renders each
# panel through shared chart/stat/table primitives. Keep the two in sync.


class StatItem(BaseModel):
    label: str
    value: float | str
    unit: str | None = None
    hint: str | None = None


class StatPanel(BaseModel):
    type: Literal["stat"] = "stat"
    title: str | None = None
    stats: Annotated[list[StatItem], Field(min_length=1)]


class SeriesPoint(BaseModel):
    x: str  # ISO date or category label
    y: float


class Series(BaseModel):
    key: str
    label: str | None = None
    points: list[SeriesPoint]


class TimeSeriesPanel(BaseModel):
    type: Literal["timeseries"] = "timeseries"
    title: str | None = None
    series: Annotated[list[Series], Field(min_length=1)]


class HistogramBin(BaseModel):
    label: str
    count: int


class HistogramPanel(BaseModel):
    type: Literal["histogram"] = "histogram"
    title: str | None = None
    bins: Annotated[list[HistogramBin], Field(min_length=1)]


class TableColumn(BaseModel):
    key: str
    header: str
    align: Literal["left", "right"] | None = None


class TablePanel(BaseModel):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: Annotated[list[TableColumn], Field(min_length=1)]
    rows: list[dict[str, str | float]]


Panel = Annotated[
    StatPanel | TimeSeriesPanel | HistogramPanel | TablePanel,
    Field(discriminator="type"),
]


class DashboardSpec(BaseModel):
    title: str | None = None
    layout: Literal["stack", "grid", "columns"] = "stack"
    panels: Annotated[list[Panel], Field(min_length=1)]


@tool
def render_dashboard(spec: DashboardSpec) -> dict:
    """Render a composed insights dashboard in the chat from a structured spec.

    This is the tool for *visualizing* results once you've computed them: it
    combines multiple panels into one vetted layout (the browser draws each via
    shared chart/stat/table primitives). Pass the data inline — this tool does
    not re-fetch. A typical field-health dashboard pairs a seasonal-index
    ``timeseries`` with ``stat`` tiles and a ``histogram`` from zonal stats.

    Panels (discriminated by ``type``):
      - ``stat``: {type, title?, stats: [{label, value, unit?, hint?}]}
      - ``timeseries``: {type, title?, series: [{key, label?, points: [{x, y}]}]}
        where ``x`` is an ISO date/category string and ``y`` is a number.
      - ``histogram``: {type, title?, bins: [{label, count}]}
      - ``table``: {type, title?, columns: [{key, header, align?}], rows: [{...}]}

    Args:
        spec: ``layout`` (``stack`` | ``grid`` | ``columns``) plus the ordered
            list of ``panels`` to render, with their data inline.
    """
    return {"queued_dashboard": True, "panel_count": len(spec.panels)}


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
