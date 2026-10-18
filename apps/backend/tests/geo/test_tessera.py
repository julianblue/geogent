"""Offline tests for the TESSERA reader: pure helpers plus the production
:class:`IcechunkTesseraReader` against an in-memory Icechunk repo (no network)."""

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from geogent_backend.geo import tessera
from geogent_backend.geo.tessera import IcechunkTesseraReader
from tests.tessera_fakes import X0, Y0, field_geometry_4326

# --------------------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    "lon,lat,group",
    [(16.6, 48.25, "33N"), (-122.4, 37.8, "10N"), (151.2, -33.9, "56S"), (0.0, 0.0, "31N")],
)
def test_zone_group_for(lon: float, lat: float, group: str) -> None:
    assert tessera.zone_group_for(lon, lat) == group


def test_bbox_zone_group_rejects_a_zone_crossing_bbox() -> None:
    assert tessera.bbox_zone_group((16.58, 48.24, 16.62, 48.27)) == "33N"
    with pytest.raises(tessera.TesseraZoneError, match="33N"):
        tessera.bbox_zone_group((11.9, 47.0, 12.1, 47.1))  # Austria's 12°E seam


def test_expand_bbox_m_is_latitude_corrected_and_clamped() -> None:
    west, south, east, north = tessera.expand_bbox_m((16.0, 48.0, 16.1, 48.1), 1000)
    assert north - 0.1 == pytest.approx(48.0 + 1000 / 110_540, rel=1e-3)
    assert 16.0 - west > 1000 / 111_320  # a degree of lon is shorter than of lat at 48°N
    assert tessera.expand_bbox_m((16.0, 48.0, 16.1, 48.1), 0) == (16.0, 48.0, 16.1, 48.1)
    assert tessera.expand_bbox_m((-179.99, 89.99, 179.99, 90.0), 5000)[3] == 90.0


def test_bbox_to_window_snaps_out_to_the_grid() -> None:
    crs = CRS.from_epsg(32633)
    aff = Affine(10.0, 0.0, X0 - 1000, 0.0, -10.0, Y0 + 1000)
    bbox = tessera.expand_bbox_m(_bounds(field_geometry_4326()), 0)
    rows, cols, win = tessera.bbox_to_window(bbox, crs, aff, 500, 500)
    # the window origin is a whole pixel on the group grid, north-up
    assert (win.c - aff.c) % 10 == 0 and (aff.f - win.f) % 10 == 0 and win.e == -10.0
    assert rows.stop - rows.start >= 20 and cols.stop - cols.start >= 20
    with pytest.raises(tessera.TesseraNoDataError):
        tessera.bbox_to_window((100.0, 10.0, 100.1, 10.1), crs, aff, 500, 500)


def test_dequantise_makes_non_finite_scales_nan() -> None:
    i8 = np.full((2, 2, 3), 10, dtype=np.int8)
    scales = np.array([[0.5, np.nan], [np.inf, 1.0]], dtype=np.float32)
    out = tessera.dequantise(i8, scales)
    assert out.shape == (3, 2, 2) and out.dtype == np.float32
    assert out[0, 0, 0] == 5.0 and out[0, 1, 1] == 10.0
    assert np.isnan(out[:, 0, 1]).all() and np.isnan(out[:, 1, 0]).all()


def test_reader_raises_unavailable_when_the_group_is_missing(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(tessera.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(tessera.TesseraUnavailableError, match="embeddings"):
        tessera.ensure_available()


def _bounds(geom: dict) -> tuple[float, float, float, float]:
    xs = [p[0] for p in geom["coordinates"][0]]
    ys = [p[1] for p in geom["coordinates"][0]]
    return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------- in-memory store

N_BANDS = 6
YEARS = [2023, 2024, 2025]
# group extent: 140 rows x 160 cols (1.4 x 1.6 km) around the planted field
ROWS, COLS = 140, 160
ORIGIN_X, ORIGIN_Y = X0 - 500.0, Y0 + 500.0


@pytest.fixture(scope="module")
def repo():  # noqa: ANN201
    """A tiny zone group ``33N`` shaped like the real store.

    ``embeddings`` = (band + 1) so dequantised values are ``(band + 1) * scale``;
    ``scales`` differ per year, and pixel (row 50, col 60) of every year is NaN.
    """
    icechunk = pytest.importorskip("icechunk")  # the `embeddings` group; skip without it
    xr = pytest.importorskip("xarray")
    repo = icechunk.Repository.create(icechunk.in_memory_storage())
    session = repo.writable_session("main")
    emb = np.broadcast_to(
        (np.arange(N_BANDS) + 1).astype(np.int8), (len(YEARS), ROWS, COLS, N_BANDS)
    ).copy()
    scales = np.stack([np.full((ROWS, COLS), 0.5 * (i + 1), np.float32) for i in range(3)])
    scales[:, 50, 60] = np.nan
    ds = xr.Dataset(
        {
            "embeddings": (("time", "northing", "easting", "band"), emb),
            "scales": (("time", "northing", "easting"), scales),
        },
        coords={
            "time": np.array([f"{y}-01-01" for y in YEARS], dtype="datetime64[ns]"),
            "northing": ORIGIN_Y - 5 - 10 * np.arange(ROWS),
            "easting": ORIGIN_X + 5 + 10 * np.arange(COLS),
            "band": np.arange(N_BANDS),
        },
        attrs={
            "spatial:transform": [10, 0, ORIGIN_X, 0, -10, ORIGIN_Y],
            "crs": "EPSG:32633",
            # 2025 is a preallocated-but-unwritten slot
            "years_complete": [2023, 2024],
        },
    )
    ds.to_zarr(session.store, group="33N", mode="w", zarr_format=3, consolidated=False)
    session.commit("fixture")
    return repo


@pytest.fixture
def reader(repo) -> IcechunkTesseraReader:  # noqa: ANN001
    return IcechunkTesseraReader(repo_factory=lambda: repo, year_threads=2)


_BBOX = tessera.expand_bbox_m(_bounds(field_geometry_4326()), 0)


def test_years_complete_comes_from_group_attrs(reader: IcechunkTesseraReader) -> None:
    assert reader.years_complete("33N") == {2023, 2024}


def test_read_window_dequantises_and_georeferences(reader: IcechunkTesseraReader) -> None:
    w = reader.read_window(_BBOX, [2023, 2024], dim=N_BANDS)
    assert w.group == "33N" and w.years == [2023, 2024] and w.crs.to_epsg() == 32633
    assert w.emb.shape[:2] == (2, N_BANDS) and w.emb.dtype == np.float32
    # (band + 1) * 0.5 in 2023, * 1.0 in 2024 — values land in the right year/band
    assert w.emb[0, :, 0, 0] == pytest.approx((np.arange(N_BANDS) + 1) * 0.5)
    assert w.emb[1, :, 0, 0] == pytest.approx((np.arange(N_BANDS) + 1) * 1.0)
    # the window affine is the group's grid shifted to the window corner
    assert w.transform.a == 10.0 and w.transform.e == -10.0
    assert (w.transform.c - ORIGIN_X) % 10 == 0 and (ORIGIN_Y - w.transform.f) % 10 == 0


def test_read_window_maps_nan_scales_to_nan_pixels(reader: IcechunkTesseraReader) -> None:
    # a bbox covering the whole group must include the planted NaN pixel
    big = tessera.expand_bbox_m(_bounds(field_geometry_4326()), 400)
    w = reader.read_window(big, [2023], dim=N_BANDS)
    nan_px = ~np.isfinite(w.emb[0]).all(axis=0)
    assert nan_px.sum() == 1
    r, c = np.argwhere(nan_px)[0]
    x, y = w.transform * (c + 0.5, r + 0.5)
    assert (x, y) == pytest.approx((ORIGIN_X + 60 * 10 + 5, ORIGIN_Y - 50 * 10 - 5))


def test_read_window_slices_dim(reader: IcechunkTesseraReader) -> None:
    w = reader.read_window(_BBOX, [2024], dim=3)
    assert w.emb.shape[1] == 3


def test_read_window_rejects_unknown_year_and_outside_extent(
    reader: IcechunkTesseraReader,
) -> None:
    with pytest.raises(tessera.TesseraError, match="1999"):
        reader.read_window(_BBOX, [1999], dim=3)
    with pytest.raises(tessera.TesseraNoDataError):
        reader.read_window((16.9, 48.0, 16.91, 48.01), [2024], dim=3)  # same zone, off-extent
    with pytest.raises(tessera.TesseraZoneError):
        reader.read_window((11.9, 47.0, 12.1, 47.1), [2024], dim=3)


def test_unknown_group_is_a_tessera_error(reader: IcechunkTesseraReader) -> None:
    with pytest.raises(tessera.TesseraError):
        reader.years_complete("99N")


def test_group_is_opened_once_within_the_ttl(repo) -> None:  # noqa: ANN001
    calls = {"n": 0}

    def factory():  # noqa: ANN202
        calls["n"] += 1
        return repo

    r = IcechunkTesseraReader(repo_factory=factory)
    r.years_complete("33N")
    r.read_window(_BBOX, [2024], dim=2)
    assert calls["n"] == 1
