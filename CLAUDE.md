# geogent

Polyglot monorepo: `apps/backend` (FastAPI + PostGIS), `apps/agent` (LangGraph
agent, Python 3.12 + uv), `apps/ui` (Next.js + pnpm).

## CI — run these before every push

CI (`.github/workflows/ci.yml`) gates PRs with exactly these commands. The one
that's easy to miss is `ruff format --check` — a separate gate from
`ruff check` (lint), and `make lint` does NOT cover it.

In `apps/backend` and `apps/agent` (each):

```bash
uv sync --all-groups
uv run ruff format --check .   # formatting gate; fix with: uv run ruff format .
uv run ruff check .            # lint gate
uv run mypy src                # advisory only (continue-on-error in CI)
uv run pytest                  # agent e2e/eval tests self-skip without OPENROUTER_API_KEY
```

In `apps/ui`:

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm exec prettier --check .
```

There is also a backend migrations smoke job: `uv run alembic upgrade head`
against `postgis/postgis:16-3.4`.

When verifying locally, check pytest's actual exit code — piping output
through `grep`/`tail` masks failures.

## Other useful commands

- `make lint` / `make test` — fan out across all apps (lint = `ruff check`
  only; run the format gate separately).
- Agent live evals: `cd apps/agent && uv run pytest -m eval -s` (needs
  `OPENROUTER_API_KEY`; not part of CI). See `apps/agent/tests/evals/README.md`
  for the eval harness, recordings, and LangSmith experiments
  (`make eval-experiment`, needs `LANGSMITH_API_KEY`).

## Conventions

- Conventional commits; release-please generates the CHANGELOGs — never edit
  them by hand.
- `apps/agent` golden eval cases live in
  `apps/agent/tests/evals/cases/core.yaml`; expectations are graded by the
  scorers in `tests/evals/`, and committed recordings give offline replay
  coverage in the normal test run.
