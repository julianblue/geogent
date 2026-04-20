# geogent — convenience targets for the polyglot monorepo.
#
# Invoke with `make <target>`. Targets fan out to the right tool in each app.

.PHONY: help up down build dev logs ps \
        install install-backend install-agent install-ui \
        dev-backend dev-agent dev-ui \
        fmt fmt-py fmt-ts \
        lint lint-py lint-ts \
        test test-backend test-agent test-ui \
        migrate revision \
        clean

help:
	@echo "geogent — common tasks"
	@echo ""
	@echo "  make up              Start full stack (compose)"
	@echo "  make down            Stop full stack"
	@echo "  make build           Rebuild all compose images"
	@echo "  make logs            Tail compose logs"
	@echo ""
	@echo "  make install         Install deps for backend, agent, and ui"
	@echo "  make dev-backend     Run backend natively (requires db from compose)"
	@echo "  make dev-agent       Run agent natively"
	@echo "  make dev-ui          Run ui natively"
	@echo ""
	@echo "  make migrate         Apply Alembic migrations"
	@echo "  make revision m=msg  Create a new Alembic revision"
	@echo ""
	@echo "  make fmt             Format all code"
	@echo "  make lint            Lint all code"
	@echo "  make test            Run all tests"

# ---------------------------------------------------------------------------
# Docker Compose
# ---------------------------------------------------------------------------
up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------
install: install-backend install-agent install-ui

install-backend:
	cd apps/backend && uv sync

install-agent:
	cd apps/agent && uv sync

install-ui:
	cd apps/ui && pnpm install

# ---------------------------------------------------------------------------
# Native dev servers
# ---------------------------------------------------------------------------
dev-backend:
	cd apps/backend && uv run uvicorn geogent_backend.main:app --reload --port 8000

dev-agent:
	cd apps/agent && uv run langgraph dev --port 2024

dev-ui:
	cd apps/ui && pnpm dev

# ---------------------------------------------------------------------------
# Alembic
# ---------------------------------------------------------------------------
migrate:
	cd apps/backend && uv run alembic upgrade head

revision:
	@if [ -z "$(m)" ]; then echo "usage: make revision m='message'"; exit 1; fi
	cd apps/backend && uv run alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------------------
# Format / Lint / Test
# ---------------------------------------------------------------------------
fmt: fmt-py fmt-ts

fmt-py:
	cd apps/backend && uv run ruff format . && uv run ruff check --fix .
	cd apps/agent   && uv run ruff format . && uv run ruff check --fix .

fmt-ts:
	cd apps/ui && pnpm format

lint: lint-py lint-ts

lint-py:
	cd apps/backend && uv run ruff check .
	cd apps/agent   && uv run ruff check .

lint-ts:
	cd apps/ui && pnpm lint

test: test-backend test-agent test-ui

test-backend:
	cd apps/backend && uv run pytest

test-agent:
	cd apps/agent && uv run pytest

test-ui:
	cd apps/ui && pnpm test --if-present

clean:
	rm -rf apps/backend/.pytest_cache apps/agent/.pytest_cache
	rm -rf apps/ui/.next apps/ui/node_modules
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
