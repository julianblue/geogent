"""Provider-layer tests for geo/routing.py.

Drives the httpx calls through MockTransport so we verify URL/param construction
and response normalisation without external network. Settings are pinned via
monkeypatch + get_settings.cache_clear so the provider reads test values.
"""

import httpx
import pytest

from geogent_backend.config import get_settings
from geogent_backend.geo import routing


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _mock(monkeypatch: pytest.MonkeyPatch, handler) -> dict:
    captured: dict = {}
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs) -> httpx.AsyncClient:  # noqa: ANN002, ANN003
        kwargs["transport"] = httpx.MockTransport(lambda req: handler(req, captured))
        return real_client(*args, **kwargs)

    monkeypatch.setattr(routing.httpx, "AsyncClient", fake_client)
    return captured


@pytest.mark.asyncio
async def test_route_builds_osrm_url_and_normalises(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request, captured: dict) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "distance": 1234.5,
                        "duration": 600.0,
                        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                    }
                ],
            },
        )

    captured = _mock(monkeypatch, handler)
    result = await routing.route([(2.35, 48.86), (2.13, 48.80)], "driving")

    assert "/route/v1/driving/2.35,48.86;2.13,48.8" in captured["url"]
    assert "geometries=geojson" in captured["url"]
    assert result["distance_m"] == 1234.5
    assert result["geometry"]["type"] == "LineString"


@pytest.mark.asyncio
async def test_route_raises_when_no_route(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request, captured: dict) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json={"code": "NoRoute", "routes": []})

    _mock(monkeypatch, handler)
    with pytest.raises(routing.RoutingError):
        await routing.route([(0.0, 0.0), (1.0, 1.0)])


@pytest.mark.asyncio
async def test_isochrone_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(routing.IsochroneUnavailableError):
        await routing.isochrone(2.29, 48.85, [600], "driving")


@pytest.mark.asyncio
async def test_isochrone_keyless_self_host_omits_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    # A self-hosted (non-public) base URL with no key must still work, without
    # an Authorization header.
    monkeypatch.setenv("ORS_API_KEY", "")
    monkeypatch.setenv("ORS_BASE_URL", "http://ors.internal:8080")
    get_settings.cache_clear()

    def handler(req: httpx.Request, captured: dict) -> httpx.Response:
        captured["auth"] = req.headers.get("Authorization")
        captured["url"] = str(req.url)
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

    captured = _mock(monkeypatch, handler)
    result = await routing.isochrone(2.29, 48.85, [600], "driving")

    assert captured["auth"] is None
    assert captured["url"].startswith("http://ors.internal:8080/v2/isochrones/")
    assert result["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_isochrone_sends_key_and_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_API_KEY", "test-key")
    get_settings.cache_clear()

    def handler(req: httpx.Request, captured: dict) -> httpx.Response:
        captured["auth"] = req.headers.get("Authorization")
        captured["url"] = str(req.url)
        return httpx.Response(200, json={"type": "FeatureCollection", "features": []})

    captured = _mock(monkeypatch, handler)
    result = await routing.isochrone(2.29, 48.85, [300, 600], "cycling")

    assert captured["auth"] == "test-key"
    assert "/v2/isochrones/cycling-regular" in captured["url"]
    assert result["type"] == "FeatureCollection"


@pytest.mark.asyncio
async def test_geocode_normalises_bbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request, captured: dict) -> httpx.Response:
        captured["path"] = req.url.path
        return httpx.Response(
            200,
            json=[
                {
                    "display_name": "Paris, France",
                    "lon": "2.3522",
                    "lat": "48.8566",
                    "type": "city",
                    # Nominatim order: [south, north, west, east].
                    "boundingbox": ["48.8", "48.9", "2.2", "2.5"],
                }
            ],
        )

    captured = _mock(monkeypatch, handler)
    results = await routing.geocode("Paris", limit=1)

    assert captured["path"].endswith("/search")
    assert results[0]["longitude"] == 2.3522
    # Normalised to [west, south, east, north].
    assert results[0]["bbox"] == [2.2, 48.8, 2.5, 48.9]


@pytest.mark.asyncio
async def test_reverse_geocode_raises_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request, captured: dict) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(200, json={"error": "Unable to geocode"})

    _mock(monkeypatch, handler)
    with pytest.raises(routing.RoutingError):
        await routing.reverse_geocode(0.0, 0.0)
