# Deploying geogent to Railway

`geogent` is a four-service stack: PostGIS, FastAPI backend, LangGraph agent,
and a Next.js UI. This guide walks through deploying all four to
[Railway](https://railway.app/) from a single GitHub repo.

## TL;DR

1. Push this repo to GitHub.
2. In Railway, create a new project from the repo and add **four services**,
   each pointing at a different root directory:

   | Service   | Root Directory          | Config              |
   | --------- | ----------------------- | ------------------- |
   | `db`      | `infra/railway/db`      | `railway.toml` ✓    |
   | `backend` | `apps/backend`          | `railway.toml` ✓    |
   | `agent`   | `apps/agent`            | `railway.toml` ✓    |
   | `ui`      | `apps/ui`               | `railway.toml` ✓    |

3. Attach a Volume to `db` at `/var/lib/postgresql/data`.
4. Set the environment variables listed below on each service.
5. Deploy. The backend will run migrations and seed a login user on first boot.
6. Open the UI's public URL and sign in.

## Default login

The backend auto-creates a user from `SEED_USER_EMAIL` / `SEED_USER_PASSWORD`
on every startup (idempotent — skipped if the user already exists). If those
variables are not set, it falls back to the defaults baked into
`apps/backend/src/geogent_backend/scripts/ensure_seed_user.py`:

- **Email:** `julian.blau@googlemail.com`
- **Password:** `Lena2046`

**Change these for any non-personal deployment.** Set `SEED_USER_EMAIL` and
`SEED_USER_PASSWORD` on the backend service in Railway *before the first
deploy* if you want different credentials seeded. Once the user is created,
changing the env vars does nothing — manage the account through the API.

## Per-service environment variables

### `db` service

```
POSTGRES_USER=geogent
POSTGRES_PASSWORD=<generate a strong password>
POSTGRES_DB=geogent
PGDATA=/var/lib/postgresql/data/pgdata
```

Attach a Volume mounted at `/var/lib/postgresql/data`. Without it, every
redeploy wipes the database. `PGDATA` must point at a subdirectory so the
mount point itself isn't used as the cluster directory (Postgres refuses that).

After the service is up, note its **private network hostname** (something
like `db.railway.internal`) — you'll reference it from the backend.

### `backend` service

```
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://geogent:<password>@<db-host>:5432/geogent
DATABASE_URL_SYNC=postgresql+psycopg://geogent:<password>@<db-host>:5432/geogent
JWT_SECRET_KEY=<generate: python -c 'import secrets; print(secrets.token_urlsafe(48))'>
CORS_ORIGINS=["https://<ui-host>.up.railway.app"]
# Optional — override the default seed user:
# SEED_USER_EMAIL=you@example.com
# SEED_USER_PASSWORD=something-strong
```

`<db-host>` is the private hostname of the `db` service (e.g.
`db.railway.internal`). Use the Railway "Variable References" feature to
template these from the db service if you prefer.

Railway will expose the backend on `https://<backend-host>.up.railway.app`.

### `agent` service

```
BACKEND_URL=https://<backend-host>.up.railway.app
AGENT_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=<your key>        # for claude-* models
# Or use one of:
# OPENAI_API_KEY=...                # for gpt-* models
# OPENROUTER_API_KEY=...            # with AGENT_MODEL=openrouter:<vendor>/<model>
# Optional tracing:
# LANGSMITH_API_KEY=...
# LANGSMITH_TRACING=true
# LANGSMITH_PROJECT=geogent
```

### `ui` service

```
BACKEND_URL=https://<backend-host>.up.railway.app
LANGGRAPH_URL=https://<agent-host>.up.railway.app
NEXT_PUBLIC_LANGGRAPH_GRAPH_ID=geogent
NODE_ENV=production
```

If you set this service's `CORS_ORIGINS` upstream on the backend, make sure
the UI's public Railway URL is included.

## Build configuration

Each service has its own `railway.toml` with the right Dockerfile and start
command — Railway picks these up automatically when you set the **Root
Directory** to the service path.

- `apps/backend/Dockerfile` runs `./scripts/start.sh` which runs Alembic
  migrations, seeds the user, then starts uvicorn on `$PORT`.
- `apps/agent/Dockerfile` runs `langgraph dev`. Note this is the in-memory
  dev server; fine for personal/demo deployments but switch to LangGraph
  Cloud or self-host with `langgraph up` for production traffic.
- `apps/ui/Dockerfile.production` does a full Next.js production build
  (`pnpm build` → `next start`). The plain `apps/ui/Dockerfile` remains for
  local docker-compose dev.
- `infra/railway/db/Dockerfile` wraps `postgis/postgis:16-3.4` so the
  database has PostGIS enabled (Railway's managed Postgres does not).

## Deploy order

1. `db` (let it come up healthy — first boot runs `init-postgis.sql`).
2. `backend` (runs migrations against `db`).
3. `agent` (talks to `backend`).
4. `ui` (talks to both).

You can deploy them all at once; Railway will keep retrying on startup
failures, so the order will sort itself out within a couple of restarts.

## Verifying

- `GET https://<backend>/api/v1/health` → `{"status": "ok", ...}`
- `POST https://<backend>/api/v1/auth/login` with the seed credentials →
  `{"access_token": "...", ...}`
- Open `https://<ui>/` → login page → sign in with the seed credentials.
