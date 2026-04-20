#!/usr/bin/env bash
# One-shot local bootstrap:
#   - creates .env files from examples if missing
#   - installs python deps for backend and agent (uv)
#   - installs js deps for ui (pnpm)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

[ -f .env ] || cp .env.example .env
[ -f apps/backend/.env ] || cp apps/backend/.env.example apps/backend/.env
[ -f apps/agent/.env ] || cp apps/agent/.env.example apps/agent/.env
[ -f apps/ui/.env.local ] || cp apps/ui/.env.local.example apps/ui/.env.local

command -v uv >/dev/null   || { echo "install uv: https://docs.astral.sh/uv/"; exit 1; }
command -v pnpm >/dev/null || { echo "install pnpm: https://pnpm.io/installation"; exit 1; }

(cd apps/backend && uv sync)
(cd apps/agent   && uv sync)
(cd apps/ui      && pnpm install)

echo "Bootstrap complete. Next: 'make up' or run dev servers individually."
