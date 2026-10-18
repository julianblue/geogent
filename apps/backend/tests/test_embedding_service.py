"""Embedding service tests with no DB, store or network.

The builders are plain sync functions over a :class:`TesseraReader`, driven here
with a :class:`FakeReader` serving planted clusters; the job/create flows swap the
repository, session factory and artifact store for in-memory fakes.
"""

import io
import json
import math
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
import pytest
from affine import Affine
from fastapi import BackgroundTasks
from rasterio.io import MemoryFile

from geogent_backend.config import Settings
from geogent_backend.geo import tessera
from geogent_backend.models.artifact import Artifact
from geogent_backend.schemas.artifact import ArtifactKind
from geogent_backend.schemas.embedding import EmbeddingLayerRecipe, FieldEmbeddingsRecipe
from geogent_backend.services import embedding_service as svc
from geogent_backend.services.artifact_service import AOITooLargeError
from geogent_backend.services.raster_service import FieldNotFoundError
from tests.tessera_fakes import DIM, X0, Y0, FakeReader, field_geometry_4326, planted_window, unit

YEARS = [2020, 2021, 2022]
# 2020 and 2021 grow crop A, 2022 crop B; every year carries its own big global offset.
_OFFSETS = {y: np.random.default_rng(y).normal(0, 4, DIM).astype(np.float32) for y in YEARS}
_CROPS = {2020: unit(1) * 3, 2021: unit(1) * 3, 2022: unit(5) * 3}


def _recipe(**over: object) -> FieldEmbeddingsRecipe:
    base = {"field_id": 7, "start_year": 2020, "end_year": 2022, "dim": DIM}
    base.update(over)
    return FieldEmbeddingsRecipe(**base)


def _reader(**kw: object) -> FakeReader:
    return FakeReader(planted_window(YEARS, _CROPS, _OFFSETS, **kw))


# --------------------------------------------------------------------------- field_embeddings


def test_build_field_embeddings_summary_and_payload() -> None:
    reader = _reader()
    summary, payload = svc.build_field_embeddings(reader, field_geometry_4326(), _recipe())

    # compact + strictly JSON-safe (JSONB rejects NaN), and no embedding vectors in it
    json.dumps(summary, allow_nan=False)
    assert "mean" not in summary and summary["payload_key"] == "field_embeddings.npz"
    assert summary["field_id"] == 7 and summary["years"] == YEARS and summary["dim"] == DIM
    assert summary["area_ha"] == pytest.approx(4.0, rel=0.02)
    assert summary["grid"] == {"epsg": 32633, "resolution_m": 10.0, "width": None, "height": None}
    assert "calendar year" in summary["assumed_window"]
    assert summary["rotation_screen"] == {"valid": True, "min_area_ha": 1.0}
    assert summary["centring"]["mode"] == "aoi" and summary["centring"]["aoi_buffer_m"] == 1000
    assert summary["centring"]["aoi_pixels_by_year"] == {"2020": 3600, "2021": 3600, "2022": 3600}
    assert summary["masking"] == {"inward_buffer_m": 10.0, "buffered": True}

    py = summary["per_year"]
    assert [p["year"] for p in py] == YEARS and all(p["usable"] for p in py)
    assert py[0]["pixel_count"] == 18 * 18 and py[0]["masked_fraction"] == 0.0
    assert set(py[0]) == {
        "year", "pixel_count", "masked_fraction", "mean_norm", "mean_std", "heterogeneity", "usable"
    }  # fmt: skip

    # same crop 2020->2021: the centred distance cancels the global offset, raw does not
    yoy = {(y["from_year"], y["to_year"]): y for y in summary["yoy"]}
    assert set(yoy) == {(2020, 2021), (2021, 2022)}
    assert yoy[(2020, 2021)]["cosine_distance_centred"] < 0.01
    assert yoy[(2020, 2021)]["cosine_distance_raw"] > 0.05
    # crop A -> crop B (orthogonal) is a large centred change
    assert yoy[(2021, 2022)]["cosine_distance_centred"] > 0.8

    # the reader got the field bbox grown by the centring buffer, and the recipe's years/dim
    ((bbox, years, dim),) = reader.read_calls
    fw, fs, fe, fn = (*np.min(field_geometry_4326()["coordinates"][0], axis=0),
                      *np.max(field_geometry_4326()["coordinates"][0], axis=0))  # fmt: skip
    assert bbox[0] < fw and bbox[1] < fs and bbox[2] > fe and bbox[3] > fn
    assert years == YEARS and dim == DIM

    z = np.load(io.BytesIO(payload))
    assert set(z.files) == {"years", "mean", "std", "pixel_count", "aoi_year_mean", "centred_mean"}
    assert z["years"].tolist() == YEARS and z["mean"].shape == (3, DIM)
    assert z["pixel_count"].tolist() == [324, 324, 324]
    assert np.allclose(z["centred_mean"], z["mean"] - z["aoi_year_mean"], atol=1e-5)


def test_build_field_embeddings_without_centring_uses_raw_means() -> None:
    summary, payload = svc.build_field_embeddings(
        _reader(), field_geometry_4326(), _recipe(centring="none")
    )
    y = summary["yoy"][0]
    assert y["cosine_distance_centred"] == pytest.approx(y["cosine_distance_raw"])
    z = np.load(io.BytesIO(payload))
    assert (z["aoi_year_mean"] == 0).all()


def test_build_field_embeddings_single_year_has_no_yoy_pairs() -> None:
    summary, _ = svc.build_field_embeddings(
        _reader(), field_geometry_4326(), _recipe(start_year=2021, end_year=2021)
    )
    assert summary["years"] == [2021] and summary["yoy"] == []
    assert len(summary["per_year"]) == 1


def test_build_field_embeddings_survives_nan_pixels() -> None:
    reader = _reader()
    emb = reader._window.emb
    emb[0, :, 25, 25] = np.nan  # one pixel inside the field in 2020
    emb[1, :, 18:42, 18:42] = np.nan  # the field (and a margin) is not embedded at all in 2021
    emb[2, 4, :, :10] = np.nan  # a NaN band along the left edge of the AOI in 2022

    summary, payload = svc.build_field_embeddings(reader, field_geometry_4326(), _recipe())
    json.dumps(summary, allow_nan=False)  # no NaN leaks into the summary

    py = {p["year"]: p for p in summary["per_year"]}
    assert py[2020]["pixel_count"] == 18 * 18 - 1 and py[2020]["usable"]
    assert py[2021]["pixel_count"] == 0 and not py[2021]["usable"]
    assert py[2021]["mean_norm"] is None and py[2021]["heterogeneity"] is None
    assert py[2021]["masked_fraction"] == 1.0
    # the AOI window loses the NaN pixels too (2021: 24x24 block; 2022: 10 columns)
    assert summary["centring"]["aoi_pixels_by_year"] == {
        "2020": 3600 - 1,
        "2021": 3600 - 24 * 24,
        "2022": 3600 - 600,
    }
    # 2021 drops out, so neither pair involving it is reported (not a fake 0 distance)
    assert summary["yoy"] == []

    z = np.load(io.BytesIO(payload))
    assert np.isnan(z["mean"][1]).all() and np.isfinite(z["mean"][[0, 2]]).all()
    assert np.isfinite(z["aoi_year_mean"]).all()  # centring never sees a NaN


def test_build_field_embeddings_flags_small_fields() -> None:
    # 4x4 px (0.16 ha): the 10 m buffer leaves 4 pixels -> unusable, rotation screen off
    summary, _ = svc.build_field_embeddings(
        _reader(), field_geometry_4326(inset_px=8), _recipe(start_year=2020, end_year=2021)
    )
    assert all(p["pixel_count"] == 4 and not p["usable"] for p in summary["per_year"])
    assert summary["rotation_screen"]["valid"] is False
    assert summary["yoy"] == []


def test_build_field_embeddings_fails_when_a_year_is_not_complete() -> None:
    reader = FakeReader(planted_window(YEARS, _CROPS, _OFFSETS), complete={2020, 2021})
    with pytest.raises(tessera.TesseraError, match="2022"):
        svc.build_field_embeddings(reader, field_geometry_4326(), _recipe())
    assert reader.read_calls == []  # failed before any read


def test_dim_slices_the_window() -> None:
    summary, payload = svc.build_field_embeddings(_reader(), field_geometry_4326(), _recipe(dim=4))
    assert summary["dim"] == 4 and np.load(io.BytesIO(payload))["mean"].shape == (3, 4)


# --------------------------------------------------------------------------- embedding_layer


def _layer_recipe(**over: object) -> EmbeddingLayerRecipe:
    base = {"year": 2021, "field_id": 7, "dim": DIM}
    base.update(over)
    return EmbeddingLayerRecipe(**base)


def test_build_embedding_layer_writes_a_tiled_rgb_cog() -> None:
    reader = _reader(noise=0.05)
    bbox = (16.3, 48.1, 16.4, 48.2)
    summary, cog = svc.build_embedding_layer(reader, bbox, _layer_recipe())

    json.dumps(summary, allow_nan=False)
    assert summary["mode"] == "pca" and summary["year"] == 2021 and summary["dim"] == DIM
    assert len(summary["explained_variance_ratio"]) == 3
    assert summary["valid_fraction"] == 1.0
    assert summary["grid"] == {"epsg": 32633, "resolution_m": 10.0, "width": 60, "height": 60}
    west, south, east, north = summary["bbox_wgs84"]
    assert west < east and south < north and 16.0 < west < 17.0 and 48.0 < south < 49.0
    assert summary["stretch"] == "p2–p98 per component; valid 1..255; 0=nodata"
    assert "calendar year" in summary["assumed_window"]
    assert reader.read_calls[0][1] == [2021]

    with MemoryFile(cog) as mem, mem.open() as ds:
        assert ds.count == 3 and ds.dtypes == ("uint8",) * 3 and ds.nodata == 0
        assert ds.crs.to_epsg() == 32633 and (ds.width, ds.height) == (60, 60)
        assert ds.block_shapes[0] == (256, 256)  # always tiled
        assert ds.read().min() >= 1


def test_build_embedding_layer_nan_pixels_become_nodata() -> None:
    reader = _reader(noise=0.05)
    reader._window.emb[1, :, :10, :] = np.nan
    summary, cog = svc.build_embedding_layer(reader, (16.3, 48.1, 16.4, 48.2), _layer_recipe())
    assert summary["valid_fraction"] == pytest.approx(50 / 60)
    with MemoryFile(cog) as mem, mem.open() as ds:
        rgb = ds.read()
        assert (rgb[:, :10] == 0).all() and (rgb[:, 10:] >= 1).all()


def test_build_embedding_layer_without_embeddings_is_a_no_data_error() -> None:
    reader = _reader()
    reader._window.emb[1] = np.nan
    with pytest.raises(tessera.TesseraNoDataError):
        svc.build_embedding_layer(reader, (16.3, 48.1, 16.4, 48.2), _layer_recipe())


def test_layer_bbox_variants() -> None:
    geom = field_geometry_4326()
    padded = svc.layer_bbox(geom, _layer_recipe(pad_m=500))
    bare = svc.layer_bbox(geom, _layer_recipe(pad_m=0))
    assert padded[0] < bare[0] and padded[3] > bare[3]
    assert svc.layer_bbox(None, EmbeddingLayerRecipe(year=2021, bbox=(1, 2, 3, 4))) == (1, 2, 3, 4)
    wkt_recipe = EmbeddingLayerRecipe(
        year=2021, geometry_wkt="POLYGON((16 48,16.1 48,16.1 48.1,16 48))"
    )
    assert svc.layer_bbox(None, wkt_recipe) == (16.0, 48.0, 16.1, 48.1)


# --------------------------------------------------------------------------- create / dedup


class FakeRepo:
    """In-memory stand-in for ArtifactRepository covering what the service calls."""

    def __init__(self, existing: Artifact | None = None) -> None:
        self.row = existing
        self.reset_calls: list[str] = []
        self.created: list[tuple] = []
        self.hashed: list[tuple[str, dict]] = []  # (recipe_hash, stored recipe)
        self.results: list[tuple] = []
        self.errors: list[str] = []
        self.statuses: list[str] = []

    async def get_by_recipe(self, owner, h):  # noqa: ANN001, ANN202
        return self.row

    async def get(self, artifact_id):  # noqa: ANN001, ANN202
        return self.row

    async def create_or_get(self, artifact_id, kind, h, recipe, owner):  # noqa: ANN001, ANN202
        self.row = Artifact(
            id=artifact_id, kind=kind, recipe_hash=h, status="pending", recipe=recipe, owner=owner
        )
        self.created.append((artifact_id, kind))
        self.hashed.append((h, recipe))
        return self.row

    async def reset_failed(self, artifact_id):  # noqa: ANN001, ANN202
        self.reset_calls.append(artifact_id)
        assert self.row is not None
        if self.row.status != "failed":
            return False
        self.row.status, self.row.error = "pending", None
        return True

    async def set_status(self, artifact_id, status):  # noqa: ANN001, ANN202
        self.statuses.append(status)

    async def set_result(self, artifact_id, summary, assets):  # noqa: ANN001, ANN202
        self.results.append((artifact_id, summary, assets))

    async def set_error(self, artifact_id, error):  # noqa: ANN001, ANN202
        self.errors.append(error)


class MemStore:
    def __init__(self) -> None:
        self.puts: dict[tuple[str, str], bytes] = {}

    async def put(self, artifact_id, key, data):  # noqa: ANN001, ANN202
        self.puts[(artifact_id, key)] = data
        return f"mem://{artifact_id}/{key}"


def _service(
    repo: FakeRepo, store: MemStore | None = None, **settings: object
) -> svc.EmbeddingService:
    s = svc.EmbeddingService(
        session=None,  # type: ignore[arg-type]
        owner="1",
        reader=_reader(noise=0.05),
        store=store or MemStore(),  # type: ignore[arg-type]
        settings=Settings(**settings),
    )
    s._repo = repo  # type: ignore[assignment]
    return s


def _row(status: str, error: str | None = None) -> Artifact:
    return Artifact(
        id="abc", kind="field_embeddings", recipe_hash="h", status=status, recipe={}, error=error
    )


@pytest.fixture
def field_geom(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(session, field_id):  # noqa: ANN001, ANN202
        if field_id == 404:
            raise FieldNotFoundError("Field 404 not found")
        return field_geometry_4326()

    monkeypatch.setattr(svc, "_field_geometry", fake)


async def test_create_dispatches_a_new_build(field_geom: None) -> None:
    repo, bg = FakeRepo(), BackgroundTasks()
    row, cached = await _service(repo).create_field_embeddings(_recipe(), bg)
    assert not cached and row.status == "pending" and repo.created[0][1] == "field_embeddings"
    assert len(bg.tasks) == 1


@pytest.mark.parametrize("status", ["pending", "running", "succeeded"])
async def test_create_reuses_a_non_failed_row(field_geom: None, status: str) -> None:
    repo, bg = FakeRepo(_row(status)), BackgroundTasks()
    row, cached = await _service(repo).create_field_embeddings(_recipe(), bg)
    assert cached and row.status == status and not bg.tasks and not repo.reset_calls


async def test_create_resets_and_redispatches_a_failed_row(field_geom: None) -> None:
    repo, bg = FakeRepo(_row("failed", "TESSERA upstream error: boom")), BackgroundTasks()
    row, cached = await _service(repo).create_field_embeddings(_recipe(), bg)
    assert repo.reset_calls == ["abc"]
    assert not cached and row.status == "pending" and row.error is None
    assert len(bg.tasks) == 1  # the same artifact id is rebuilt, not a new row
    assert not repo.created


async def test_create_layer_resets_a_failed_row_too(field_geom: None) -> None:
    repo, bg = FakeRepo(_row("failed", "x")), BackgroundTasks()
    row, cached = await _service(repo).create_embedding_layer(_layer_recipe(), bg)
    assert not cached and len(bg.tasks) == 1


async def test_create_unknown_field_is_not_found(field_geom: None) -> None:
    with pytest.raises(FieldNotFoundError):
        await _service(FakeRepo()).create_field_embeddings(_recipe(field_id=404), BackgroundTasks())


async def test_create_rejects_oversized_and_cross_zone_windows(field_geom: None) -> None:
    repo = FakeRepo()
    small = _service(repo, tessera_layer_max_pixels=1000)
    with pytest.raises(AOITooLargeError, match="pixel-years"):
        await small.create_field_embeddings(_recipe(), BackgroundTasks())
    with pytest.raises(AOITooLargeError):
        await _service(repo).create_embedding_layer(
            EmbeddingLayerRecipe(year=2021, bbox=(16.0, 48.0, 17.0, 49.0)), BackgroundTasks()
        )
    with pytest.raises(tessera.TesseraZoneError):
        await _service(repo).create_embedding_layer(
            EmbeddingLayerRecipe(year=2021, bbox=(11.99, 47.0, 12.01, 47.01)), BackgroundTasks()
        )
    assert not repo.created


async def test_pixel_cap_counts_the_projected_utm_window(field_geom: None) -> None:
    # Thin sliver near the 18 E edge of zone 33N: meridians converge there, so the
    # enclosing UTM rectangle is ~4x the lon/lat rectangle's pixel count.
    bbox = (17.90, 47.0, 17.902, 47.1)
    naive = math.ceil(0.002 * 111_320 * math.cos(math.radians(47.05)) / 10) * math.ceil(
        0.1 * 110_540 / 10
    )
    rows, cols = tessera.estimate_window_shape(bbox)
    assert naive < 30_000 < rows * cols  # passes a lon/lat-rectangle check, fails the real one

    repo = FakeRepo()
    s = _service(repo, tessera_layer_max_pixels=30_000)
    with pytest.raises(AOITooLargeError, match="pixel-years"):
        await s.create_embedding_layer(
            EmbeddingLayerRecipe(year=2021, bbox=bbox), BackgroundTasks()
        )
    assert not repo.created
    # the same sliver on the zone's central meridian is within budget
    ok = (15.0, 47.0, 15.002, 47.1)
    assert math.prod(tessera.estimate_window_shape(ok)) < 30_000
    await s.create_embedding_layer(EmbeddingLayerRecipe(year=2021, bbox=ok), BackgroundTasks())
    assert len(repo.created) == 1


def test_window_estimate_bounds_what_the_reader_reads() -> None:
    crs = tessera.zone_crs("33N")
    assert crs.to_epsg() == 32633 and tessera.zone_crs("56S").to_epsg() == 32756
    bbox = tessera.expand_bbox_m(_bounds_of(field_geometry_4326()), 0)
    aff = Affine(10.0, 0.0, X0 - 1003.0, 0.0, -10.0, Y0 + 1007.0)  # off-grid origin
    rows, cols, _ = tessera.bbox_to_window(bbox, crs, aff, 500, 500)
    est_rows, est_cols = tessera.estimate_window_shape(bbox)
    assert rows.stop - rows.start <= est_rows and cols.stop - cols.start <= est_cols


def _bounds_of(geom: dict) -> tuple[float, float, float, float]:
    xs = [p[0] for p in geom["coordinates"][0]]
    ys = [p[1] for p in geom["coordinates"][0]]
    return min(xs), min(ys), max(xs), max(ys)


async def test_store_identity_is_server_side_and_part_of_the_cache_key(field_geom: None) -> None:
    async def make(settings: dict, **recipe: object) -> tuple[str, dict]:
        repo = FakeRepo()
        await _service(repo, **settings).create_field_embeddings(
            _recipe(**recipe), BackgroundTasks()
        )
        return repo.hashed[0]

    base = await make({})
    # the caller cannot choose the cache key through store_version ...
    assert await make({}, store_version="attacker-chosen") == base
    # ... while repointing the configured store does change it
    assert (await make({"tessera_prefix": "v2/other.icechunk"}))[0] != base[0]
    assert (await make({"tessera_bucket": "elsewhere"}))[0] != base[0]
    assert (await make({"tessera_branch": "next"}))[0] != base[0]
    assert base[1]["store_version"] == "s3://tessera-embeddings/v1.1/dclimate.icechunk@main"


# --------------------------------------------------------------------------- jobs


@pytest.fixture
def job_env(monkeypatch: pytest.MonkeyPatch, field_geom: None):  # noqa: ANN201
    """Route the background job's own session/repo to in-memory fakes."""
    repo = FakeRepo()

    @asynccontextmanager
    async def fake_session():  # noqa: ANN202
        yield object()

    import geogent_backend.db.session as db_session

    monkeypatch.setattr(db_session, "SessionLocal", fake_session)
    monkeypatch.setattr(svc, "ArtifactRepository", lambda session: repo)
    monkeypatch.setattr(svc, "_read_pool", None)
    yield repo
    if svc._read_pool is not None:
        svc._read_pool.shutdown(wait=False, cancel_futures=True)


async def test_field_embeddings_job_stores_payload_with_no_assets(job_env: FakeRepo) -> None:
    store = MemStore()
    s = _service(job_env, store)
    await s._build_field_embeddings("abc", _recipe())
    assert job_env.statuses == ["running"] and not job_env.errors
    ((artifact_id, summary, assets),) = job_env.results
    assert assets == [] and summary["payload_key"] == "field_embeddings.npz"
    assert ("abc", "field_embeddings.npz") in store.puts


async def test_embedding_layer_job_declares_the_pca_rgb_asset(job_env: FakeRepo) -> None:
    store = MemStore()
    s = _service(job_env, store)
    s._reader = _reader(noise=0.05)
    await s._build_embedding_layer(
        "abc", EmbeddingLayerRecipe(year=2021, bbox=(16.3, 48.1, 16.4, 48.2))
    )
    ((_, summary, assets),) = job_env.results
    assert assets == [
        {
            "role": "pca_rgb",
            "key": "pca_rgb.tif",
            "url": "/api/v1/analytics/artifacts/abc/assets/pca_rgb.tif",
            "media_type": "image/tiff; application=geotiff",
            "colormap": "rgb",
            "label": "Embedding PCA (2021)",
            "bands": ["pc1", "pc2", "pc3"],
        }
    ]
    assert ("abc", "pca_rgb.tif") in store.puts and summary["year"] == 2021


class _BrokenReader:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def years_complete(self, group: str) -> set[int]:
        raise self._exc

    def read_window(self, *a: object) -> None:
        raise self._exc


@pytest.mark.parametrize(
    "exc,message",
    [
        (tessera.TesseraError("S3 503"), "TESSERA upstream error: S3 503"),
        (tessera.TesseraNoDataError("No TESSERA embeddings here"), "No TESSERA embeddings here"),
        (RuntimeError("secret internals"), "Artifact build failed."),
    ],
)
async def test_job_failures_end_in_a_failed_row(
    job_env: FakeRepo, exc: Exception, message: str
) -> None:
    s = _service(job_env)
    s._reader = _BrokenReader(exc)  # type: ignore[assignment]
    await s._build_field_embeddings("abc", _recipe())
    await s._build_embedding_layer(
        "abc", EmbeddingLayerRecipe(year=2021, bbox=(16.3, 48.1, 16.4, 48.2))
    )
    assert job_env.errors == [message, message] and not job_env.results


async def test_job_for_a_missing_year_fails_with_the_year_named(job_env: FakeRepo) -> None:
    s = _service(job_env)
    s._reader = FakeReader(planted_window(YEARS, _CROPS, _OFFSETS), complete={2020})
    await s._build_field_embeddings("abc", _recipe())
    assert "2021" in job_env.errors[0] and job_env.errors[0].startswith("TESSERA upstream error")


async def test_slow_read_times_out_into_a_failed_row(job_env: FakeRepo) -> None:
    class Slow(FakeReader):
        def years_complete(self, group: str) -> set[int]:
            time.sleep(0.5)
            return super().years_complete(group)

    s = _service(job_env, tessera_timeout_seconds=0.05)
    s._reader = Slow(planted_window(YEARS, _CROPS, _OFFSETS))
    await s._build_field_embeddings("abc", _recipe())
    assert "timed out" in job_env.errors[0]


async def test_timed_out_reads_keep_their_slot_until_the_thread_ends(job_env: FakeRepo) -> None:
    """A deadline frees the caller, not the worker: with one slot, the next read must
    wait for the abandoned one instead of running alongside it."""
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "ran": 0}

    def read(seconds: float) -> None:
        with lock:
            state["active"] += 1
            state["ran"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(seconds)
        with lock:
            state["active"] -= 1

    s = _service(job_env, tessera_max_concurrent_reads=1, tessera_timeout_seconds=0.05)
    with pytest.raises(TimeoutError):
        await s._offload(read, 0.4)  # abandoned at 0.05 s, thread still sleeping
    assert state["active"] == 1

    # queued behind the stuck read; its own deadline expires while it waits, so it
    # is cancelled in the queue and never starts
    with pytest.raises(TimeoutError):
        await s._offload(read, 0.0)
    assert state["ran"] == 1

    # a patient caller runs only once the stuck thread is done
    s._settings = Settings(tessera_max_concurrent_reads=1, tessera_timeout_seconds=5.0)
    await s._offload(read, 0.0)
    assert state["peak"] == 1 and state["ran"] == 2 and state["active"] == 0


def test_new_kinds_exist() -> None:
    assert ArtifactKind("field_embeddings") and ArtifactKind("embedding_layer")
