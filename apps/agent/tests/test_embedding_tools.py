"""Unit tests for the TESSERA embedding @tool wrappers.

Like test_tools.py, the backend client is replaced with one driven by
``httpx.MockTransport`` so no backend is required.
"""

import json

import httpx
import pytest

from geogent_agent.tools import (
    embedding_layer,
    embedding_tools,
    field_embedding_profile,
    show_embedding_layer,
)


def _install_mock_backend(monkeypatch: pytest.MonkeyPatch, handler) -> dict:
    captured: dict = {}

    def make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: handler(req, captured)),
            base_url="http://backend.test",
        )

    monkeypatch.setattr(
        "geogent_agent.tools.embedding_tools.get_backend_client",
        make_client,
    )
    return captured


@pytest.mark.asyncio
async def test_field_embedding_profile_polls_until_succeeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polls = {"n": 0}

    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/analytics/field-embeddings":
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(
                202,
                json={
                    "artifact_id": "emb1234",
                    "kind": "field_embeddings",
                    "status": "pending",
                    "cached": False,
                },
            )
        if request.method == "GET" and request.url.path == "/api/v1/analytics/artifacts/emb1234":
            polls["n"] += 1
            if polls["n"] == 1:
                return httpx.Response(200, json={"id": "emb1234", "status": "running"})
            return httpx.Response(
                200,
                json={
                    "id": "emb1234",
                    "kind": "field_embeddings",
                    "status": "succeeded",
                    "summary": {
                        "field_id": 12,
                        "years": [2020, 2021],
                        "yoy": [
                            {
                                "from_year": 2020,
                                "to_year": 2021,
                                "cosine_distance_centred": 0.41,
                                "cosine_distance_raw": 0.12,
                            }
                        ],
                        "rotation_screen": {"valid": True, "min_area_ha": 1.0},
                    },
                    "assets": [],
                    "error": None,
                },
            )
        return httpx.Response(404, json={"detail": "unexpected path"})

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(embedding_tools, "_EMBEDDING_POLL_INTERVAL_SECONDS", 0)

    result = await field_embedding_profile.ainvoke(
        {"field_id": 12, "start_year": 2020, "end_year": 2021}
    )

    assert captured["start_body"] == {
        "kind": "field_embeddings",
        "field_id": 12,
        "start_year": 2020,
        "end_year": 2021,
    }
    assert polls["n"] == 2
    assert result["artifact_id"] == "emb1234"
    assert result["kind"] == "field_embeddings"
    assert result["status"] == "succeeded"
    assert result["summary"]["yoy"][0]["cosine_distance_centred"] == 0.41
    assert result["error"] is None
    assert "assets" not in result


@pytest.mark.asyncio
async def test_field_embedding_profile_raises_on_failed_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request, _captured: dict) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                202,
                json={"artifact_id": "dead", "kind": "field_embeddings", "status": "pending"},
            )
        return httpx.Response(
            200,
            json={
                "id": "dead",
                "kind": "field_embeddings",
                "status": "failed",
                "error": "TESSERA upstream error: years_complete missing 2019",
            },
        )

    _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(embedding_tools, "_EMBEDDING_POLL_INTERVAL_SECONDS", 0)

    with pytest.raises(RuntimeError, match="years_complete missing 2019"):
        await field_embedding_profile.ainvoke(
            {"field_id": 12, "start_year": 2019, "end_year": 2021}
        )


@pytest.mark.asyncio
async def test_backend_422_detail_reaches_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, _captured: dict) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": "span 12 years exceeds tessera_max_years (9)"},
        )

    _install_mock_backend(monkeypatch, handler)

    with pytest.raises(RuntimeError) as excinfo:
        await field_embedding_profile.ainvoke(
            {"field_id": 12, "start_year": 2010, "end_year": 2021}
        )

    assert str(excinfo.value) == "422: span 12 years exceeds tessera_max_years (9)"


@pytest.mark.asyncio
async def test_embedding_layer_times_out_while_running(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, _captured: dict) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                202,
                json={"artifact_id": "slow", "kind": "embedding_layer", "status": "pending"},
            )
        return httpx.Response(200, json={"id": "slow", "status": "running"})

    _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(embedding_tools, "_EMBEDDING_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(embedding_tools, "_EMBEDDING_POLL_TIMEOUT_SECONDS", 0)

    with pytest.raises(TimeoutError, match="slow"):
        await embedding_layer.ainvoke({"year": 2024, "field_id": 12})


@pytest.mark.asyncio
async def test_embedding_layer_sends_bbox_and_no_field_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        if request.method == "POST":
            captured["start_path"] = request.url.path
            captured["start_body"] = json.loads(request.content)
            return httpx.Response(
                202,
                json={"artifact_id": "lay1", "kind": "embedding_layer", "status": "pending"},
            )
        return httpx.Response(
            200,
            json={
                "id": "lay1",
                "kind": "embedding_layer",
                "status": "succeeded",
                "summary": {
                    "mode": "pca",
                    "year": 2024,
                    "explained_variance_ratio": [0.4, 0.2, 0.1],
                },
                "assets": [{"role": "pca_rgb", "key": "pca_rgb.tif", "url": "/x"}],
                "error": None,
            },
        )

    captured = _install_mock_backend(monkeypatch, handler)
    monkeypatch.setattr(embedding_tools, "_EMBEDDING_POLL_INTERVAL_SECONDS", 0)

    result = await embedding_layer.ainvoke(
        {"year": 2024, "bbox": [13.75, 53.20, 14.05, 53.40], "pad_m": 0}
    )

    assert captured["start_path"] == "/api/v1/analytics/embedding-layers"
    assert captured["start_body"] == {
        "kind": "embedding_layer",
        "mode": "pca",
        "year": 2024,
        "pad_m": 0,
        "bbox": [13.75, 53.20, 14.05, 53.40],
    }
    assert result["artifact_id"] == "lay1"
    assert result["summary"]["year"] == 2024
    assert "assets" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {"year": 2024},
        {"year": 2024, "field_id": 12, "bbox": [13.75, 53.20, 14.05, 53.40]},
    ],
    ids=["neither", "both"],
)
async def test_embedding_layer_rejects_bad_aoi_without_calling_backend(
    monkeypatch: pytest.MonkeyPatch, args: dict
) -> None:
    def handler(request: httpx.Request, captured: dict) -> httpx.Response:
        captured.setdefault("requests", []).append(request.url.path)
        return httpx.Response(500, json={"detail": "should not be called"})

    captured = _install_mock_backend(monkeypatch, handler)

    with pytest.raises(ValueError, match="exactly one of field_id or bbox"):
        await embedding_layer.ainvoke(args)

    assert "requests" not in captured


@pytest.mark.asyncio
async def test_show_embedding_layer_returns_ack_only() -> None:
    result = await show_embedding_layer.ainvoke({"artifact_id": "lay1", "label": "PCA 2024"})

    assert result == {
        "queued_embedding_layer": True,
        "artifact_id": "lay1",
        "mode": "pca",
        "label": "PCA 2024",
    }
