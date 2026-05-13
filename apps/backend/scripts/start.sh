#!/usr/bin/env sh
# Production startup for the geogent backend on Railway (and any other
# container host). Runs Alembic migrations, ensures the seed user exists,
# then hands off to uvicorn.
set -eu

echo "[start.sh] running alembic migrations"
uv run alembic upgrade head

echo "[start.sh] ensuring seed user"
uv run python -m geogent_backend.scripts.ensure_seed_user || true

PORT="${PORT:-8000}"
echo "[start.sh] launching uvicorn on 0.0.0.0:${PORT}"
exec uv run uvicorn geogent_backend.main:app --host 0.0.0.0 --port "${PORT}"
