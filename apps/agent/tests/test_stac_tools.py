"""Unit tests for the STAC @tool wrappers.

We replace ``_stac_client`` with one driven by ``httpx.MockTransport`` so
tests don't hit the real Earth Search endpoint. Each test handler captures
the request so we can assert on URL, method, and body.
"""

import json

import httpx
import pytest

from geogent_agent.tools import stac_get_item, stac_list_collections, stac_search
from geogent_agent.tools.stac_tools import DEFAULT_STAC_API


def _install_mock_stac(monkeypatch: pytest.MonkeyPatch, handler) -> dict:
    """Replace ``_stac_client`` with a MockTransport-backed client.

    The handler receives ``(httpx.Request, captured: dict)`` and returns a
    response. ``captured`` is shared across all calls in the test.
    """
    captured: dict = {}

    def make_client(api_url: str | None) -> httpx.AsyncClient:
        captured.setdefault("base_urls", []).append((api_url or DEFAULT_STAC_API).rstrip("/"))
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: handler(req, captured)),
            base_url=(api_url or DEFAULT_STAC_API).rstrip("/"),
        )

    monkeypatch.setattr("geogent_agent.tools.stac_tools._stac_client", make_client)
    return captured


@pytest.mark.asyncio
async def test_list_collections_uses_default_api(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "collections": [
                    {"id": "sentinel-2-l2a", "title": "Sentinel-2 L2A", "description": "..."},
                    {"id": "landsat-c2-l2", "title": "Landsat C2 L2", "description": "..."},
                ]
            },
        )

    captured = _install_mock_stac(monkeypatch, handler)
    result = await stac_list_collections.ainvoke({})

    assert captured["method"] == "GET"
    assert captured["path"].endswith("/collections")
    assert captured["base_urls"] == [DEFAULT_STAC_API]
    assert result == [
        {"id": "sentinel-2-l2a", "title": "Sentinel-2 L2A", "description": "..."},
        {"id": "landsat-c2-l2", "title": "Landsat C2 L2", "description": "..."},
    ]


@pytest.mark.asyncio
async def test_list_collections_respects_explicit_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request, _captured: dict) -> httpx.Response:
        return httpx.Response(200, json={"collections": []})

    captured = _install_mock_stac(monkeypatch, handler)
    await stac_list_collections.ainvoke({"api_url": "https://example.com/stac/"})

    assert captured["base_urls"] == ["https://example.com/stac"]


@pytest.mark.asyncio
async def test_search_posts_only_provided_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"features": []})

    captured = _install_mock_stac(monkeypatch, handler)
    await stac_search.ainvoke(
        {
            "collections": ["sentinel-2-l2a"],
            "bbox": [-122.52, 37.70, -122.36, 37.83],
            "datetime": "2024-07-01/2024-07-31",
            "limit": 5,
        }
    )

    assert captured["method"] == "POST"
    assert captured["path"].endswith("/search")
    assert captured["body"] == {
        "limit": 5,
        "collections": ["sentinel-2-l2a"],
        "bbox": [-122.52, 37.70, -122.36, 37.83],
        "datetime": "2024-07-01/2024-07-31",
    }


@pytest.mark.asyncio
async def test_search_intersects_wins_over_bbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"features": []})

    captured = _install_mock_stac(monkeypatch, handler)
    geom = {"type": "Point", "coordinates": [-122.42, 37.77]}
    await stac_search.ainvoke(
        {
            "bbox": [-122.52, 37.70, -122.36, 37.83],
            "intersects": geom,
        }
    )

    assert "bbox" not in captured["body"]
    assert captured["body"]["intersects"] == geom


@pytest.mark.asyncio
async def test_search_trims_items(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request, _captured: dict) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "id": "S2A_T10SEG_20240715",
                        "collection": "sentinel-2-l2a",
                        "bbox": [-122.5, 37.7, -122.3, 37.85],
                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]},
                        "properties": {
                            "datetime": "2024-07-15T18:55:21Z",
                            "eo:cloud_cover": 12.3,
                            "platform": "sentinel-2a",
                            "constellation": "sentinel-2",
                            "instruments": ["msi"],
                            "gsd": 10,
                            "proj:epsg": 32610,
                            "view:sun_elevation": 60.5,
                            "ignore_me": "noise",
                        },
                        "assets": {
                            "red": {"href": "s3://...", "type": "image/tiff"},
                            "green": {"href": "s3://..."},
                            "thumbnail": {"href": "https://..."},
                        },
                    }
                ]
            },
        )

    _install_mock_stac(monkeypatch, handler)
    result = await stac_search.ainvoke({"collections": ["sentinel-2-l2a"]})

    assert result == [
        {
            "id": "S2A_T10SEG_20240715",
            "collection": "sentinel-2-l2a",
            "bbox": [-122.5, 37.7, -122.3, 37.85],
            "properties": {
                "datetime": "2024-07-15T18:55:21Z",
                "eo:cloud_cover": 12.3,
                "platform": "sentinel-2a",
                "constellation": "sentinel-2",
                "instruments": ["msi"],
                "gsd": 10,
                "proj:epsg": 32610,
            },
            "asset_keys": ["green", "red", "thumbnail"],
        }
    ]


@pytest.mark.asyncio
async def test_search_accepts_string_encoded_intersects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some Bedrock tool-call serializers emit nested objects as JSON strings."""

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"features": []})

    captured = _install_mock_stac(monkeypatch, handler)
    geom = {"type": "Point", "coordinates": [-122.42, 37.77]}
    await stac_search.ainvoke({"intersects": json.dumps(geom)})

    assert captured["body"]["intersects"] == geom


@pytest.mark.asyncio
async def test_search_accepts_string_encoded_bbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"features": []})

    captured = _install_mock_stac(monkeypatch, handler)
    await stac_search.ainvoke({"bbox": "[-122.52, 37.70, -122.36, 37.83]"})

    assert captured["body"]["bbox"] == [-122.52, 37.70, -122.36, 37.83]


@pytest.mark.asyncio
async def test_search_forwards_sortby_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """`sortby` + `query` are the difference between getting latest cloud-free
    Sentinel-2 vs an arbitrary slice of the archive — verify they reach the
    wire."""

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"features": []})

    captured = _install_mock_stac(monkeypatch, handler)
    await stac_search.ainvoke(
        {
            "collections": ["sentinel-2-l2a"],
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
            "query": {"eo:cloud_cover": {"lt": 20}},
        }
    )

    assert captured["body"]["sortby"] == [
        {"field": "properties.datetime", "direction": "desc"}
    ]
    assert captured["body"]["query"] == {"eo:cloud_cover": {"lt": 20}}


@pytest.mark.asyncio
async def test_search_accepts_string_encoded_sortby_and_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"features": []})

    captured = _install_mock_stac(monkeypatch, handler)
    await stac_search.ainvoke(
        {
            "sortby": '[{"field": "properties.datetime", "direction": "desc"}]',
            "query": '{"eo:cloud_cover": {"lt": 20}}',
        }
    )

    assert captured["body"]["sortby"] == [
        {"field": "properties.datetime", "direction": "desc"}
    ]
    assert captured["body"]["query"] == {"eo:cloud_cover": {"lt": 20}}


@pytest.mark.asyncio
async def test_get_item_hits_correct_path(monkeypatch: pytest.MonkeyPatch) -> None:
    full_item = {
        "id": "S2A_T10SEG_20240715",
        "collection": "sentinel-2-l2a",
        "assets": {"red": {"href": "s3://bucket/red.tif"}},
        "properties": {"datetime": "2024-07-15T18:55:21Z"},
    }

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=full_item)

    captured = _install_mock_stac(monkeypatch, handler)
    result = await stac_get_item.ainvoke(
        {"collection": "sentinel-2-l2a", "item_id": "S2A_T10SEG_20240715"}
    )

    assert captured["path"].endswith("/collections/sentinel-2-l2a/items/S2A_T10SEG_20240715")
    assert result == full_item


@pytest.mark.asyncio
async def test_search_surfaces_backend_error_with_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 4xx/5xx from the STAC API should propagate as a ValueError that
    includes the API's own error body, so the calling LLM can retry with a
    fixed payload rather than just seeing 'HTTPStatusError'."""

    def handler(_request: httpx.Request, _captured: dict) -> httpx.Response:
        return httpx.Response(400, json={"detail": "sortby field unknown"})

    _install_mock_stac(monkeypatch, handler)

    with pytest.raises(ValueError) as exc:
        await stac_search.ainvoke(
            {
                "collections": ["sentinel-2-l2a"],
                "sortby": [{"field": "bogus", "direction": "desc"}],
            }
        )

    msg = str(exc.value)
    assert "HTTP 400" in msg
    assert "sortby field unknown" in msg
    assert "bogus" in msg  # the offending payload is included for context
