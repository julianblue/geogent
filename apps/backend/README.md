# geogent-backend

FastAPI service that owns persistence, auth, and PostGIS queries for geogent.

## Stack

- FastAPI + Pydantic v2
- SQLAlchemy 2.0 async + `asyncpg`
- GeoAlchemy2 + Shapely for geospatial types
- Alembic migrations (async)
- Managed with [`uv`](https://docs.astral.sh/uv/)

## Run locally

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn geogent_backend.main:app --reload --port 8000
```

OpenAPI docs: <http://localhost:8000/docs>

## Layout

```
src/geogent_backend/
├── main.py          # app factory, ASGI entrypoint
├── config.py        # pydantic-settings
├── api/
│   ├── deps.py      # DI: db session, auth
│   └── v1/
│       ├── router.py
│       └── routes/  # health, features, analytics
├── db/              # engine + session
├── models/          # SQLAlchemy + GeoAlchemy2 models
├── schemas/         # Pydantic request/response
├── services/        # business logic
├── repositories/    # data access
├── geo/             # PostGIS / shapely helpers
└── core/            # logging, errors
```

## EuroCrops parcel data (Germany / Brandenburg)

The `fields` table can be loaded with real crop parcels from
[EuroCrops](https://github.com/maja601/EuroCrops) (CC-BY-4.0; Schneider et
al., data on [Zenodo record 10118572](https://zenodo.org/records/10118572)).
Each parcel becomes a field: harmonized HCAT crop name in `crop` (e.g.
`winter_common_soft_wheat`), declaration year in `season`. The agent queries
them via `/fields/in-bbox` (crop/limit filters) and `/fields/crop-stats`
(per-crop parcel count + hectares for a bbox).

A 400-parcel Brandenburg/Uckermark sample (clip of `DE_BB_2023`, bbox
`13.75,53.20 → 14.05,53.40`) is committed at
`data/eurocrops_de_bb_2023_sample.geojson`:

```bash
uv run --group ingest scripts/ingest_eurocrops.py \
    --source data/eurocrops_de_bb_2023_sample.geojson
```

For a bigger clip, download a region zip from Zenodo (DE_BB ~103 MB,
DE_NRW ~277 MB, DE_LS ~241 MB) and ingest with `--bbox` (always clip — a full
region is hundreds of thousands of parcels) and `--exclude-noncrop`:

```bash
uv run --group ingest scripts/ingest_eurocrops.py \
    --source /path/to/DE_BB_2023.shp \
    --bbox 13.75,53.20,14.05,53.40 --exclude-noncrop --limit 2000
```
