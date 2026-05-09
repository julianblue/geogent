"""STAC API tools.

Direct ``httpx`` calls against any STAC-compliant API for catalog and item
discovery. Mirrors the ``osm_tools`` pattern — no backend proxy, no new
dependency. The default endpoint is Earth Search v1 hosted by Element 84,
which exposes Sentinel-1/-2, Landsat, NAIP, and global DEMs.
"""

from typing import Any

import httpx
from langchain_core.tools import tool

DEFAULT_STAC_API = "https://earth-search.aws.element84.com/v1"
USER_AGENT = "geogent-agent/0.1 (https://github.com/julianblue/geogent)"


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
    interesting_props = {
        k: v
        for k, v in props.items()
        if k in {"datetime", "start_datetime", "end_datetime", "eo:cloud_cover", "platform"}
    }
    return {
        "id": item.get("id"),
        "collection": item.get("collection"),
        "datetime": props.get("datetime"),
        "bbox": item.get("bbox"),
        "properties": interesting_props,
        "asset_keys": sorted((item.get("assets") or {}).keys()),
    }


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
        r.raise_for_status()
        body = r.json()
    collections = body.get("collections") or []
    return [_trim_collection(c) for c in collections]


@tool
async def stac_search(
    collections: list[str] | None = None,
    bbox: list[float] | None = None,
    datetime: str | None = None,
    intersects: dict | None = None,
    limit: int = 10,
    api_url: str | None = None,
) -> list[dict]:
    """Search items across one or more STAC collections.

    Args:
        collections: STAC collection IDs to search (e.g. ``["sentinel-2-l2a"]``).
            Use ``stac_list_collections`` to discover available IDs.
        bbox: Bounding box ``[west, south, east, north]`` in WGS84 degrees.
            Mutually exclusive with ``intersects``; if both are passed,
            ``intersects`` wins and ``bbox`` is dropped.
        datetime: ISO 8601 instant or interval. Examples: ``"2024-07-01"``,
            ``"2024-07-01/2024-07-31"``, ``"2024-07-01/.."`` for open-ended.
        intersects: GeoJSON geometry dict (Point, Polygon, etc.) the
            returned items must intersect.
        limit: Max items to return from the first page (no pagination
            follow-through). Default 10.
        api_url: Root URL of the STAC API. Defaults to Earth Search v1.

    Returns:
        Trimmed item dicts: ``{id, collection, datetime, bbox, properties, asset_keys}``.
        Use ``stac_get_item`` to fetch the full item with asset hrefs.
    """
    payload: dict[str, Any] = {"limit": limit}
    if collections:
        payload["collections"] = collections
    if intersects is not None:
        payload["intersects"] = intersects
    elif bbox is not None:
        payload["bbox"] = bbox
    if datetime is not None:
        payload["datetime"] = datetime

    async with _stac_client(api_url) as client:
        r = await client.post("/search", json=payload)
        r.raise_for_status()
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
        r = await client.get(f"/collections/{collection}/items/{item_id}")
        r.raise_for_status()
        return r.json()
