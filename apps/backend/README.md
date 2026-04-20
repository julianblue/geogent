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
