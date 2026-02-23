#!/usr/bin/env bash
# Run the same Python-related CI steps locally (lint + test server).
# Requires: uv, Python 3.12, Node 20 (for frontend steps), and optionally
# PostgreSQL + Redis for server tests (or use docker via ./scripts/dev-up.sh).
set -e

cd "$(dirname "$0")/.."
ROOT="$PWD"

echo "==> Lint (Python)"
uv sync --all-packages --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy packages/

echo "==> Test (Server)"
if [ -z "${MC_DATABASE_URL}" ]; then
  export MC_DATABASE_URL="${MC_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@localhost:5432/mission_control_test}"
  export MC_REDIS_URL="${MC_REDIS_URL:-redis://localhost:6379/0}"
  echo "Using MC_DATABASE_URL=$MC_DATABASE_URL MC_REDIS_URL=$MC_REDIS_URL"
  echo "Start Postgres and Redis first (e.g. ./scripts/dev-up.sh) if needed."
fi
export MC_SECRET_KEY="${MC_SECRET_KEY:-test-secret-key}"
uv run pytest packages/server -v

echo "==> Python CI steps passed."
