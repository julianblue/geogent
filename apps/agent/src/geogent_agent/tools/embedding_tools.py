"""TESSERA field-embedding tools: per-year profiles and PCA false-colour layers.

Both tools start a backend artifact job and poll it to completion, the same
POST + poll pattern as ``field_memory_for_field``. The heavy pixels never come
back to the model; only the artifact summary does.
"""

import asyncio
import json
import time
from typing import Any, Literal

import httpx
from langchain_core.tools import tool

from geogent_agent.tools.backend_client import get_backend_client

# Embedding jobs read several years of an icechunk store, so they get the same
# budget as the field-memory build. Module constants, not tool args.
_EMBEDDING_POLL_INTERVAL_SECONDS = 0.5
_EMBEDDING_POLL_TIMEOUT_SECONDS = 180.0


def _backend_error(exc: httpx.HTTPStatusError) -> RuntimeError:
    """Re-raise a backend HTTP error with its JSON ``detail`` so the model can act on it."""
    response = exc.response
    try:
        body = response.json()
    except ValueError:
        body = None
    detail: Any = body.get("detail", response.text) if isinstance(body, dict) else response.text
    if not isinstance(detail, str):
        detail = json.dumps(detail)
    return RuntimeError(f"{response.status_code}: {detail}")


async def _run_artifact_job(path: str, recipe: dict[str, Any], label: str) -> dict:
    """POST a recipe to ``path`` and poll its artifact until it succeeds or fails."""
    async with get_backend_client() as client:
        try:
            start = await client.post(path, json=recipe)
            start.raise_for_status()
            artifact_id = start.json()["artifact_id"]
            deadline = time.monotonic() + _EMBEDDING_POLL_TIMEOUT_SECONDS

            while True:
                status_resp = await client.get(f"/api/v1/analytics/artifacts/{artifact_id}")
                status_resp.raise_for_status()
                result = status_resp.json()
                status = result.get("status")
                if status == "succeeded":
                    # Assets are dropped: they are render URLs for the browser, not data.
                    return {
                        "artifact_id": result.get("id", artifact_id),
                        "kind": result.get("kind"),
                        "status": status,
                        "summary": result.get("summary"),
                        "error": result.get("error"),
                    }
                if status == "failed":
                    error = result.get("error") or f"{label} {artifact_id} failed"
                    raise RuntimeError(str(error))
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"{label} {artifact_id} did not finish before timeout")
                await asyncio.sleep(_EMBEDDING_POLL_INTERVAL_SECONDS)
        except httpx.HTTPStatusError as exc:
            raise _backend_error(exc) from exc


@tool
async def field_embedding_profile(field_id: int, start_year: int, end_year: int) -> dict:
    """Profile how a field's TESSERA embeddings change from year to year.

    Builds per-year embedding statistics for one stored field over the calendar
    years ``start_year`` to ``end_year`` (inclusive). Returns ``{artifact_id,
    kind, status, summary, error}``; answer from ``summary``:

    - ``per_year`` → pixel count, masked fraction, mean norm, heterogeneity, and
      ``usable`` (false when the field has fewer than 5 pixels in that year).
    - ``yoy`` → cosine distance between consecutive usable years (unusable years
      are omitted), both ``centred`` (the surrounding area's per-year mean
      removed, cancelling the global year-to-year offset so the field's own
      change stands out) and ``raw``. Distances range 0–2 and are relative:
      compare years within the field rather than against a fixed cut-off. A
      large centred distance suggests a real change in the land cover, such as
      a crop rotation.
    - ``rotation_screen`` → ``valid`` and ``min_area_ha``.

    Rules for interpreting the result:

    - Years are calendar years (Jan 1 to Dec 31). A winter crop sown in autumn
      and harvested in summer straddles two embeddings, so it can look like a
      change even when the crop did not rotate.
    - The rotation screen is only valid for parcels of at least 1 ha
      (``rotation_screen.valid``). For smaller parcels, do not report a rotation
      verdict.
    - Never interpret embeddings alone. Pair the result with
      ``seasonal_index_time_series_for_field`` for the same field and years
      before you say what changed on the ground.

    Args:
        field_id: The stored field to profile.
        start_year: First calendar year (2017 or later).
        end_year: Last calendar year, inclusive.
    """
    return await _run_artifact_job(
        "/api/v1/analytics/field-embeddings",
        {
            "kind": "field_embeddings",
            "field_id": field_id,
            "start_year": start_year,
            "end_year": end_year,
        },
        label="field-embedding build",
    )


@tool
async def embedding_layer(
    year: int,
    field_id: int | None = None,
    bbox: list[float] | None = None,
    mode: Literal["pca"] = "pca",
    pad_m: int = 200,
) -> dict:
    """Build a PCA false-colour map of TESSERA embeddings for one calendar year.

    Projects the 128-band embedding for a single calendar year (Jan 1 to Dec 31)
    onto three principal components and returns a 3-band raster. Returns
    ``{artifact_id, kind, status, summary, error}``. The pixels are never
    returned to you; answer from ``summary`` (``explained_variance_ratio``,
    ``valid_fraction``, ``grid``, ``bbox_wgs84``).

    Pass EITHER ``field_id`` (a stored field, drawn with ``pad_m`` metres of
    context around it) OR ``bbox`` ``[min_lon, min_lat, max_lon, max_lat]`` for
    an arbitrary area. Exactly one of the two.

    Rules for interpreting and displaying the result:

    - PCA colours are not comparable across years. The component signs are
      arbitrary and the stretch is set per layer, so the same colour in 2023 and
      2024 does not mean the same crop. Compare years through
      ``field_embedding_profile``, not by eye on two layers.
    - Never interpret the colours alone. Pair the layer with
      ``seasonal_index_time_series_for_field`` for the same field and year before
      you say what a colour represents.
    - To draw it on the map, pass the returned ``artifact_id`` to
      ``show_embedding_layer``.

    Args:
        year: The calendar year to embed (2017 or later).
        field_id: A stored field to draw. Use this OR ``bbox``.
        bbox: ``[min_lon, min_lat, max_lon, max_lat]`` in WGS84. Use this OR ``field_id``.
        mode: Only ``pca`` is supported.
        pad_m: Metres of context around ``field_id``. Ignored for ``bbox``.
    """
    if (field_id is None) == (bbox is None):
        raise ValueError("provide exactly one of field_id or bbox")
    aoi: dict[str, Any] = {"field_id": field_id} if field_id is not None else {"bbox": bbox}
    return await _run_artifact_job(
        "/api/v1/analytics/embedding-layers",
        {"kind": "embedding_layer", "mode": mode, "year": year, "pad_m": pad_m, **aoi},
        label="embedding layer build",
    )
