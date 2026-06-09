"""Seed a demo agricultural field for the agriculture widgets (#24).

The field tools (`zonal_stats_for_field`, `seasonal_index_time_series_for_field`)
and their UI widgets need a real `field_id` whose polygon sits over an area with
dependable Sentinel-2 L2A coverage — otherwise the time-series job returns no
points and the demo looks broken.

The default polygon is a ~1 km² block in California's San Joaquin Valley (near
Lemoore / Hanford), prime irrigated cropland with year-round, low-cloud
Sentinel-2 coverage. Override with --name / --crop / --season as needed.

Idempotent: skips creation if a field with the same name already exists.

Usage:
    uv run python -m geogent_backend.scripts.seed_field
    uv run python -m geogent_backend.scripts.seed_field --name "South block" --crop cotton
"""

import argparse
import asyncio

from geogent_backend.db.session import SessionLocal
from geogent_backend.schemas.field import FieldCreate
from geogent_backend.services.field_service import FieldService

# San Joaquin Valley demo parcel (lon, lat), WGS84. ~1.1 km × 0.9 km rectangle
# over irrigated cropland west of Hanford, CA — chosen for reliable, low-cloud
# Sentinel-2 coverage across a full growing season.
_DEMO_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [
            [-119.7200, 36.3300],
            [-119.7080, 36.3300],
            [-119.7080, 36.3380],
            [-119.7200, 36.3380],
            [-119.7200, 36.3300],
        ]
    ],
}


async def _seed(name: str, crop: str | None, season: str | None) -> int:
    async with SessionLocal() as session:
        service = FieldService(session)
        existing = await service.list_fields()
        match = next((f for f in existing if f.name == name), None)
        if match is not None:
            print(f"field already exists id={match.id} name={match.name!r} (skipping)")
            return 0
        field = await service.create_field(
            FieldCreate(name=name, crop=crop, season=season, geometry=_DEMO_GEOMETRY)
        )
    print(f"created field id={field.id} name={field.name!r} crop={field.crop!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a demo agricultural field.")
    parser.add_argument("--name", default="Demo field — San Joaquin Valley")
    parser.add_argument("--crop", default="cotton")
    parser.add_argument("--season", default="2025")
    args = parser.parse_args()
    return asyncio.run(_seed(args.name, args.crop, args.season))


if __name__ == "__main__":
    raise SystemExit(main())
