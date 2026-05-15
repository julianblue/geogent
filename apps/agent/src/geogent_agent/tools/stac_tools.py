"""STAC API tools.

Direct ``httpx`` calls against any STAC-compliant API for catalog and item
discovery. Mirrors the ``osm_tools`` pattern — no backend proxy, no new
dependency. The default endpoint is Earth Search v1 hosted by Element 84,
which exposes Sentinel-1/-2, Landsat, NAIP, and global DEMs.
"""

import json
from typing import Any

import httpx
from langchain_core.tools import tool

DEFAULT_STAC_API = "https://earth-search.aws.element84.com/v1"
USER_AGENT = "geogent-agent/0.1 (https://github.com/julianblue/geogent)"

# Properties small enough to keep in trimmed search results so the agent can
# reason about resolution, sensor, projection without an extra get_item call.
_INTERESTING_PROPS = frozenset(
    {
        "datetime",
        "start_datetime",
        "end_datetime",
        "eo:cloud_cover",
        "platform",
        "constellation",
        "instruments",
        "gsd",
        "proj:epsg",
    }
)


def _stac_client(api_url: str | None) -> httpx.AsyncClient:
    """Build an ``httpx.AsyncClient`` bound to the requested STAC root URL.

    Exposed at module scope so tests can monkeypatch it with a
    ``MockTransport``-backed client.
    """
    base = (api_url or DEFAULT_STAC_API).rstrip("/")
    return httpx.AsyncClient(
        base_url=base,
        timeout=30.0,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


def _trim_collection(c: dict) -> dict:
    return {
        "id": c.get("id"),
        "title": c.get("title"),
        "description": c.get("description"),
    }


def _trim_item(item: dict) -> dict:
    """Reduce a STAC Item to the fields the agent typically needs.

    Full assets are dropped to keep token usage bounded — call
    ``stac_get_item`` to retrieve them for a chosen item.
    """
    props = item.get("properties") or {}
    interesting_props = {k: v for k, v in props.items() if k in _INTERESTING_PROPS}
    return {
        "id": item.get("id"),
        "collection": item.get("collection"),
        "bbox": item.get("bbox"),
        "properties": interesting_props,
        "asset_keys": sorted((item.get("assets") or {}).keys()),
    }


def _coerce_optional_json(value: Any) -> Any:
    """Pass JSON-shaped values through; decode JSON strings; preserve None.

    Some LLM tool-call serializers (notably stricter Bedrock paths) emit a
    JSON string in place of a nested object/array. This helper lets every
    nested-shape parameter accept either form transparently.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _coerce_geojson(value: Any) -> dict | None:
    """``_coerce_optional_json`` + assert the result is a GeoJSON-shaped dict."""
    coerced = _coerce_optional_json(value)
    if coerced is None or isinstance(coerced, dict):
        return coerced
    raise TypeError(
        f"intersects must be a GeoJSON object or JSON string, got {type(value).__name__}"
    )


def _coerce_bbox(value: Any) -> list[float] | None:
    """Tolerate string-encoded bbox arrays from LLM tool-call serializers."""
    coerced = _coerce_optional_json(value)
    if coerced is None:
        return None
    if not isinstance(coerced, list | tuple):
        raise TypeError(f"bbox must be a list of floats or JSON string, got {type(value).__name__}")
    return [float(x) for x in coerced]


def _raise_for_stac(r: httpx.Response, *, endpoint: str, payload: Any = None) -> None:
    """Convert a 4xx/5xx STAC response into a ValueError that includes the
    API's own complaint plus the request payload.

    We raise ValueError (not HTTPStatusError) so that langgraph's tool error
    handler hands the message to the LLM as a tool result — the agent can
    then self-correct on a malformed payload instead of just seeing
    'HTTPStatusError'.
    """
    if r.status_code < 400:
        return
    try:
        detail = r.json()
    except ValueError:
        detail = r.text
    suffix = f". Sent payload: {payload}" if payload is not None else ""
    raise ValueError(
        f"STAC API rejected {endpoint} (HTTP {r.status_code}): {detail}{suffix}"
    )


@tool
async def stac_list_collections(api_url: str | None = None) -> list[dict]:
    """List collections available on a STAC API.

    Args:
        api_url: Root URL of the STAC API. Defaults to Earth Search v1
            (``https://earth-search.aws.element84.com/v1``) which hosts
            Sentinel-1/-2, Landsat, NAIP and DEM collections.

    Returns:
        List of ``{id, title, description}`` per collection.
    """
    async with _stac_client(api_url) as client:
        r = await client.get("/collections")
        _raise_for_stac(r, endpoint="/collections")
        body = r.json()
    collections = body.get("collections") or []
    return [_trim_collection(c) for c in collections]


@tool
async def stac_search(
    collections: list[str] | None = None,
    bbox: list[float] | str | None = None,
    datetime: str | None = None,
    intersects: dict | str | None = None,
    limit: int = 10,
    sortby: list[dict] | str | None = None,
    query: dict | str | None = None,
    api_url: str | None = None,
) -> list[dict]:
    """Search items across one or more STAC collections.

    For "latest" / "most recent" queries you MUST pass
    ``sortby=[{"field": "properties.datetime", "direction": "desc"}]`` —
    Earth Search's default ordering is not by date and will return
    arbitrary items otherwise.

    For optical imagery (Sentinel-2, Landsat, NAIP) you almost always
    want to filter by cloud cover via
    ``query={"eo:cloud_cover": {"lt": 20}}``; without it you'll get
    100%-cloudy scenes that are useless for visual interpretation.

    Args:
        collections: STAC collection IDs to search (e.g. ``["sentinel-2-l2a"]``).
            Use ``stac_list_collections`` to discover available IDs.
        bbox: Bounding box ``[west, south, east, north]`` in WGS84 degrees.
            A JSON-string-encoded array is also accepted (some tool-call
            serializers stringify nested values). Mutually exclusive with
            ``intersects``; if both are passed, ``intersects`` wins.
        datetime: ISO 8601 instant or interval. Examples: ``"2024-07-01"``,
            ``"2024-07-01/2024-07-31"``, ``"2024-07-01/.."`` for open-ended.
        intersects: GeoJSON geometry dict (Point, Polygon, etc.) the
            returned items must intersect. JSON-string form also accepted.
        limit: Max items to return from the first page (no pagination
            follow-through). Default 10.
        sortby: STAC-API sort specifier. List of ``{"field": "...", "direction": "asc"|"desc"}``
            dicts. Example for newest first:
            ``[{"field": "properties.datetime", "direction": "desc"}]``.
            JSON-string form accepted.
        query: STAC-API ``query`` extension predicate. Maps property name to
            an operator dict. Examples:
            ``{"eo:cloud_cover": {"lt": 20}}`` —
            ``{"platform": {"eq": "sentinel-2b"}}``.
            JSON-string form accepted.
        api_url: Root URL of the STAC API. Defaults to Earth Search v1.

    Returns:
        Trimmed item dicts: ``{id, collection, bbox, properties, asset_keys}``.
        Use ``stac_get_item`` to fetch the full item with asset hrefs.
    """
    payload: dict[str, Any] = {"limit": limit}
    if collections:
        payload["collections"] = collections
    intersects_parsed = _coerce_geojson(intersects)
    bbox_parsed = _coerce_bbox(bbox)
    if intersects_parsed is not None:
        payload["intersects"] = intersects_parsed
    elif bbox_parsed is not None:
        payload["bbox"] = bbox_parsed
    if datetime is not None:
        payload["datetime"] = datetime
    sortby_parsed = _coerce_optional_json(sortby)
    if sortby_parsed is not None:
        payload["sortby"] = sortby_parsed
    query_parsed = _coerce_optional_json(query)
    if query_parsed is not None:
        payload["query"] = query_parsed

    async with _stac_client(api_url) as client:
        r = await client.post("/search", json=payload)
        _raise_for_stac(r, endpoint="/search", payload=payload)
        body = r.json()

    features = body.get("features") or []
    return [_trim_item(it) for it in features]


@tool
async def stac_get_item(
    collection: str,
    item_id: str,
    api_url: str | None = None,
) -> dict:
    """Fetch the full STAC Item for a known collection + item id.

    Returns the complete item including all asset hrefs and metadata —
    use this after ``stac_search`` narrows the candidates.

    Args:
        collection: STAC collection ID (e.g. ``"sentinel-2-l2a"``).
        item_id: Item ID returned by ``stac_search``.
        api_url: Root URL of the STAC API. Defaults to Earth Search v1.
    """
    async with _stac_client(api_url) as client:
        endpoint = f"/collections/{collection}/items/{item_id}"
        r = await client.get(endpoint)
        _raise_for_stac(r, endpoint=endpoint)
        return r.json()
