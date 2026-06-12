"""Ingest EuroCrops parcels into the geogent ``fields`` table.

EuroCrops (https://github.com/maja601/EuroCrops, data on Zenodo record
10118572) is the harmonized EU crop-parcel dataset, CC-BY-4.0:

    Schneider, M., Schelte, T., Schmitz, F. & Körner, M. EuroCrops: The
    largest harmonized open crop dataset across the European Union.
    Sci Data 10, 612 (2023). https://doi.org/10.5281/zenodo.6868143

Each parcel becomes one row in ``fields``: ``crop`` from the harmonized HCAT
name (``EC_hcat_n``), ``season`` from the declaration year, geometry
reprojected to SRID 4326. Parcels without a harmonized crop label (landscape
elements, unmaintained land) are skipped unless ``--keep-unlabeled``.

Ingest a *clip*, not a country: a whole region file is hundreds of thousands
of parcels, which the agent's listing tools are not meant to navigate.

Examples (from apps/backend, against the compose Postgres)::

    # The committed Brandenburg sample (no download needed):
    uv run --group ingest scripts/ingest_eurocrops.py \\
        --source data/eurocrops_de_bb_2023_sample.geojson

    # A fresh clip from the full Brandenburg file:
    uv run --group ingest scripts/ingest_eurocrops.py \\
        --source /path/to/DE_BB_2023.shp --bbox 13.75,53.20,14.05,53.40 --limit 2000

    # Re-export a sample GeoJSON instead of writing to the DB:
    uv run --group ingest scripts/ingest_eurocrops.py \\
        --source /path/to/DE_BB_2023.shp --bbox 13.75,53.20,14.05,53.40 \\
        --limit 300 --export-geojson data/eurocrops_de_bb_2023_sample.geojson
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import geopandas as gpd
from geoalchemy2.shape import from_shape
from shapely.validation import make_valid

from geogent_backend.models.field import Field

# EuroCrops harmonized columns (present in every country file).
HCAT_NAME = "EC_hcat_n"
TRANSLATED_NAME = "EC_trans_n"
# Per-country declaration-year column; Brandenburg uses ANTRAGJAHR. Fall back
# to --season when absent.
YEAR_COLUMNS = ("ANTRAGJAHR", "year", "YEAR")
# Per-country parcel-identifier candidates for stable, meaningful names.
ID_COLUMNS = ("REF_IDENT", "ID", "id", "fid")

BATCH_SIZE = 500

# HCAT buckets that aren't crops in any useful sense for the agent (landscape
# elements, woods, unmanaged land). Pasture and fallow stay: they're real
# agronomic land uses. Dropped by --exclude-noncrop.
NONCROP_HCAT = frozenset({"not_known_and_other", "other_tree_wood_forest", "unmaintained"})


def _bbox_in_source_crs(source: str, bbox: tuple[float, ...]) -> tuple[float, ...]:
    """Transform a lon/lat bbox into the source file's CRS so the spatial
    filter is pushed down into the GDAL read (a full country file is hundreds
    of thousands of parcels; reading it all just to clip wastes minutes and GB).
    """
    import pyogrio
    from pyproj import Transformer

    crs = pyogrio.read_info(source)["crs"]
    if crs is None or str(crs).upper() in ("EPSG:4326", "OGC:CRS84"):
        return bbox
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = transformer.transform([bbox[0], bbox[2]], [bbox[1], bbox[3]])
    return (min(xs), min(ys), max(xs), max(ys))


def load_parcels(args: argparse.Namespace) -> gpd.GeoDataFrame:
    bbox = tuple(args.bbox) if args.bbox else None
    read_bbox = _bbox_in_source_crs(args.source, bbox) if bbox else None
    df = gpd.read_file(args.source, engine="pyogrio", bbox=read_bbox)
    df = df.to_crs(4326)
    if bbox:
        # Exact clip in lon/lat: the pushed-down bbox was the (possibly larger)
        # reprojected envelope.
        df = df.cx[bbox[0] : bbox[2], bbox[1] : bbox[3]]

    if HCAT_NAME in df.columns and not args.keep_unlabeled:
        df = df[df[HCAT_NAME].notna()]
    if args.exclude_noncrop and HCAT_NAME in df.columns:
        df = df[~df[HCAT_NAME].isin(NONCROP_HCAT)]
    if args.crop:
        if HCAT_NAME not in df.columns:
            sys.exit(f"--crop given but source has no {HCAT_NAME} column")
        df = df[df[HCAT_NAME].str.contains(args.crop, case=False, na=False)]

    df = df[df.geometry.notna()]
    df = df[df.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if args.limit:
        df = df.head(args.limit)
    return df


def parcel_rows(df: gpd.GeoDataFrame, args: argparse.Namespace) -> list[Field]:
    year_col = next((c for c in YEAR_COLUMNS if c in df.columns), None)
    id_col = next((c for c in ID_COLUMNS if c in df.columns), None)
    rows: list[Field] = []
    for i, rec in enumerate(df.itertuples(index=False), start=1):
        crop = getattr(rec, HCAT_NAME, None) if hasattr(rec, HCAT_NAME) else None
        ident = getattr(rec, id_col) if id_col else f"{i:06d}"
        season = args.season or (str(getattr(rec, year_col)) if year_col else None)
        geom = rec.geometry if rec.geometry.is_valid else make_valid(rec.geometry)
        rows.append(
            Field(
                name=f"{args.name_prefix} {ident}",
                crop=str(crop) if crop is not None else None,
                season=season,
                geometry=from_shape(geom, srid=4326),
            )
        )
    return rows


async def insert(rows: list[Field]) -> None:
    # Imported lazily so --export-geojson / --dry-run work without a DB.
    from geogent_backend.db.session import SessionLocal

    async with SessionLocal() as session:
        for start in range(0, len(rows), BATCH_SIZE):
            session.add_all(rows[start : start + BATCH_SIZE])
            await session.commit()
            print(f"  inserted {min(start + BATCH_SIZE, len(rows))}/{len(rows)}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        required=True,
        help="EuroCrops vector file (.shp/.gpkg/.geojson, zip paths work via GDAL)",
    )
    parser.add_argument(
        "--bbox",
        type=lambda s: [float(x) for x in s.split(",")],
        default=None,
        metavar="MIN_LON,MIN_LAT,MAX_LON,MAX_LAT",
        help="clip to a lon/lat bbox (strongly recommended on full country files)",
    )
    parser.add_argument("--crop", default=None, help="HCAT crop-name substring filter")
    parser.add_argument("--limit", type=int, default=None, help="max parcels to ingest")
    parser.add_argument("--season", default=None, help="override season (default: source year)")
    parser.add_argument("--name-prefix", default="DE-BB", help="prefix for generated field names")
    parser.add_argument("--keep-unlabeled", action="store_true")
    parser.add_argument(
        "--exclude-noncrop",
        action="store_true",
        help=f"drop non-crop HCAT buckets: {sorted(NONCROP_HCAT)}",
    )
    parser.add_argument("--dry-run", action="store_true", help="report what would be ingested")
    parser.add_argument(
        "--export-geojson",
        type=Path,
        default=None,
        help="write the filtered parcels to GeoJSON instead of inserting into the DB",
    )
    args = parser.parse_args(argv)

    df = load_parcels(args)
    if df.empty:
        sys.exit("no parcels matched the filters")
    crops = df[HCAT_NAME].value_counts().head(10).to_dict() if HCAT_NAME in df.columns else {}
    print(f"[eurocrops] {len(df)} parcels selected; top crops: {crops}")

    if args.export_geojson is not None:
        args.export_geojson.parent.mkdir(parents=True, exist_ok=True)
        # Slim to the columns ingestion reads, at ~10cm coordinate precision,
        # so a committed sample stays small.
        keep = [c for c in (*ID_COLUMNS, *YEAR_COLUMNS, TRANSLATED_NAME, HCAT_NAME) if c in df]
        df[[*keep, "geometry"]].to_file(
            args.export_geojson, driver="GeoJSON", engine="pyogrio", COORDINATE_PRECISION=6
        )
        print(f"[eurocrops] wrote {args.export_geojson}")
        return 0
    if args.dry_run:
        print("[eurocrops] dry run, nothing inserted")
        return 0

    rows = parcel_rows(df, args)
    asyncio.run(insert(rows))
    print(f"[eurocrops] done: {len(rows)} fields inserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
