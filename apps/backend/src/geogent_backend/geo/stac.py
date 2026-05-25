"""STAC client for discovering Sentinel-2 scenes.

Thin ``httpx`` wrapper over the Earth Search v1 catalog (same contract the UI
and agent already use): ``sentinel-2-l2a`` collection, cloud filter via the
``query`` extension, ``sortby`` on ``properties.datetime``. Returns full STAC
items so callers can read band hrefs off ``item["assets"][key]["href"]``.
"""

from __future__ import annotations

import re
from datetime import date

import httpx

from geogent_backend.config import get_settings

_USER_AGENT = "geogent-backend/0.3 (raster-compute)"

# STAC collection ids and item ids are single URL path segments. Constrain them
# to an unambiguous character set so a caller-supplied id cannot smuggle path
# separators or traversal sequences into the request URL (SSRF).
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class StacError(Exception):
    """A STAC request failed or returned no usable result."""


def _safe_segment(value: str, what: str) -> str:
    if not _PATH_SEGMENT_RE.fullmatch(value):
        raise StacError(f"Invalid STAC {what}.")
    return value


def _client() -> httpx.AsyncClient:
    base = get_settings().stac_api_url.rstrip("/")
    return httpx.AsyncClient(
        base_url=base,
        timeout=30.0,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )


def _collection() -> str:
    return get_settings().stac_collection


async def find_scene(
    bbox: list[float],
    datetime: str | None = None,
    max_cloud_cover: float = 20,
) -> dict:
    """Newest low-cloud scene intersecting ``bbox`` (most recent first).

    ``datetime`` is an optional STAC datetime instant/interval to constrain the
    search. Returns the full STAC item, or raises :class:`StacError` if none
    match.
    """
    payload: dict = {
        "collections": [_collection()],
        "bbox": bbox,
        "query": {"eo:cloud_cover": {"lt": max_cloud_cover}},
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        "limit": 1,
    }
    if datetime is not None:
        payload["datetime"] = datetime

    async with _client() as client:
        resp = await client.post("/search", json=payload)
        resp.raise_for_status()
        features = resp.json().get("features") or []

    if not features:
        raise StacError("No matching Sentinel-2 scene found for the requested field/date.")
    return features[0]


async def search_scenes(
    bbox: list[float],
    start_date: date,
    end_date: date,
    max_cloud_cover: float = 20,
    limit: int = 60,
) -> list[dict]:
    """All low-cloud scenes intersecting ``bbox`` over a date range, oldest first."""
    payload: dict = {
        "collections": [_collection()],
        "bbox": bbox,
        "datetime": f"{start_date.isoformat()}T00:00:00Z/{end_date.isoformat()}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud_cover}},
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
        "limit": limit,
    }
    async with _client() as client:
        resp = await client.post("/search", json=payload)
        resp.raise_for_status()
        return resp.json().get("features") or []


async def get_item(collection: str, item_id: str) -> dict:
    """Fetch a single full STAC item by collection + id."""
    collection = _safe_segment(collection, "collection")
    item_id = _safe_segment(item_id, "item id")
    async with _client() as client:
        resp = await client.get(f"/collections/{collection}/items/{item_id}")
        resp.raise_for_status()
        return resp.json()
