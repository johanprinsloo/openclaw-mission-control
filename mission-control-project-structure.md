# Mission Control Project Structure and Build Pipeline

This document defines how the Mission Control codebase is organized, built, tested, deployed, and published. It covers the server, frontend, Comms Bridge plugin, and shared packages.

## Repository Strategy: Monorepo

All Mission Control components live in a single repository. This is the right choice at the current scale because:

- The server and Bridge share API schemas, event types, and error codes. A single repo keeps these in sync without cross-repo version coordination.
- A single CI pipeline validates that server changes don't break the Bridge (and vice versa).
- Contributors can see and understand the full system in one place.
- Independent component versioning is still possible within a monorepo using per-package version files.

The repository uses a **Python workspace** (via `uv` workspaces) for the backend components and a separate **npm workspace** for the frontend.

---

## Directory Structure

```
mission-control/
│
├── packages/
│   ├── server/                         # Mission Control server (FastAPI)
│   │   ├── app/
│   │   │   ├── api/v1/                 # Route handlers
│   │   │   ├── auth/                   # OIDC, API key, JWT
│   │   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── schemas/                # Pydantic request/response (imports from shared)
│   │   │   ├── services/               # Business logic
│   │   │   ├── realtime/               # SSE and WebSocket managers
│   │   │   ├── core/                   # Config, database, security, middleware
│   │   │   └── main.py                 # App factory
│   │   ├── alembic/                    # Database migrations
│   │   │   └── versions/
│   │   ├── tests/
│   │   │   ├── api/                    # Route integration tests
│   │   │   ├── services/               # Business logic unit tests
│   │   │   ├── realtime/               # SSE/WebSocket tests
│   │   │   └── conftest.py
│   │   ├── pyproject.toml              # Server package definition
│   │   └── README.md
│   │
│   ├── bridge/                         # Comms Bridge plugin
│   │   ├── openclaw_mc_bridge/
│   │   │   ├── sse.py                  # SSE client and reconnection logic
│   │   │   ├── relay.py                # Message relay (inbound/outbound)
│   │   │   ├── commands.py             # Command routing (/status, /compact)
│   │   │   ├── sessions.py             # Session mapping and lifecycle
│   │   │   ├── subscriptions.py        # Subscription management
│   │   │   ├── sub_agents.py           # Sub-agent credential relay and lifecycle
│   │   │   ├── state.py                # Local SQLite state management
│   │   │   ├── credentials.py          # Credential provider (env, AWS SM, Vault)
│   │   │   ├── health.py               # Health and metrics endpoint
│   │   │   ├── config.py               # Pydantic config model
│   │   │   ├── update.py               # Version check and update logic
│   │   │   └── main.py                 # Entry point, signal handling, lifecycle
│   │   ├── tests/
│   │   │   ├── test_sse.py             # SSE reconnection, cursor resume
│   │   │   ├── test_relay.py           # Message translation and delivery
│   │   │   ├── test_commands.py        # Command routing
│   │   │   ├── test_sessions.py        # Session mapping lifecycle
│   │   │   ├── test_sub_agents.py      # Sub-agent spawn/terminate
│   │   │   ├── test_state.py           # SQLite persistence
│   │   │   ├── test_credentials.py     # Credential loading and masking
│   │   │   └── conftest.py
│   │   ├── pyproject.toml              # Bridge package definition
│   │   └── README.md
│   │
│   └── shared/                         # Shared types and constants
│       ├── openclaw_mc_shared/
│       │   ├── events.py               # Event type definitions and payloads
│       │   ├── schemas/                # Pydantic models shared between server and bridge
│       │   │   ├── projects.py
│       │   │   ├── tasks.py
│       │   │   ├── channels.py
│       │   │   ├── users.py
│       │   │   ├── sub_agents.py
│       │   │   └── common.py           # Pagination, error response, etc.
│       │   ├── constants.py            # Lifecycle stages, status values, roles
│       │   └── version.py              # API version compatibility ranges
│       ├── tests/
│       │   └── test_schemas.py         # Schema validation tests
│       ├── pyproject.toml
│       └── README.md
│
├── frontend/                           # Vue 3 frontend
│   ├── src/
│   │   ├── api/                        # Generated types + client
│   │   ├── composables/
│   │   ├── stores/
│   │   ├── views/
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── router/
│   │   └── main.ts
│   ├── tests/
│   │   ├── components/
│   │   └── composables/
│   ├── e2e/                            # Playwright E2E tests
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── docker/
│   ├── server.Dockerfile
│   ├── bridge.Dockerfile
│   ├── docker-compose.yml              # Production compose
│   ├── docker-compose.dev.yml          # Dev overrides (hot reload, debug ports)
│   └── docker-compose.selfhost.yml     # Self-hosted single-tenant preset
│
├── scripts/
│   ├── install.sh                      # Self-hosted one-line installer
│   ├── export-openapi.py               # Export OpenAPI spec from FastAPI app
│   └── generate-frontend-types.sh      # Run openapi-typescript against exported spec
│
├── docs/
│   ├── product-plan.md
│   ├── api-design.md
│   ├── persistence-strategy.md
│   ├── tech-stack.md
│   ├── comms-bridge-spec.md
│   └── self-hosting-guide.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml                      # Lint, type check, test (all components)
│       ├── release-server.yml          # Build + push server Docker image
│       ├── release-bridge.yml          # Build + publish Bridge to PyPI
│       ├── release-frontend.yml        # Build frontend, bundle into server image
│       └── deploy.yml                  # Deploy to hosted environment
│
├── pyproject.toml                      # Root workspace config (uv workspace)
├── uv.lock                             # Workspace-wide lockfile
└── README.md
```

---

## Package Dependencies

```
openclaw-mc-shared        (no external dependencies beyond Pydantic)
    ▲               ▲
    │               │
openclaw-mc-server   openclaw-mc-bridge
    │               │
    ▼               ▼
(FastAPI, SQLAlchemy,  (httpx, aiosqlite,
 asyncpg, etc.)         httpx-sse, etc.)
```

The `shared` package is the only coupling between server and Bridge. It contains:

- Pydantic schemas for API request/response bodies (so the Bridge can deserialize MC API responses without redefining the models).
- Event type constants and payload schemas (so the Bridge can parse SSE events reliably).
- Lifecycle stage and status constants (so both sides agree on valid values).
- API version compatibility ranges (so the Bridge can check version compatibility on startup).

The `shared` package has minimal dependencies (Pydantic only) to keep the Bridge install lightweight.

---

## Build

### Python Packages (Server, Bridge, Shared)

All three Python packages are managed by `uv` workspaces. The root `pyproject.toml` defines the workspace:

```toml
# Root pyproject.toml
[tool.uv.workspace]
members = [
    "packages/server",
    "packages/bridge",
    "packages/shared",
]
```

Each package has its own `pyproject.toml` with dependencies and metadata:

```toml
# packages/bridge/pyproject.toml
[project]
name = "openclaw-mc-bridge"
version = "0.1.0"
dependencies = [
    "openclaw-mc-shared",
    "httpx>=0.27",
    "httpx-sse>=0.4",
    "aiosqlite>=0.20",
    "pyyaml>=6.0",
    "structlog>=24.0",
    "prometheus-client>=0.20",
]

[project.scripts]
mc-bridge = "openclaw_mc_bridge.main:run"
```

Local development installs all packages in editable mode:

```bash
uv sync                    # installs all workspace packages + dependencies
```

### Frontend

```bash
cd frontend
npm install
npm run dev                # Vite dev server with HMR
npm run build              # Production build to frontend/dist/
```

### Docker Images

Two images are built: one for the server (which bundles the frontend), one for the Bridge.

```dockerfile
# docker/server.Dockerfile
FROM python:3.12-slim
COPY packages/shared /app/packages/shared
COPY packages/server /app/packages/server
COPY frontend/dist /app/static          # Pre-built frontend
WORKDIR /app/packages/server
RUN pip install /app/packages/shared /app/packages/server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# docker/bridge.Dockerfile
FROM python:3.12-slim
COPY packages/shared /app/packages/shared
COPY packages/bridge /app/packages/bridge
WORKDIR /app/packages/bridge
RUN pip install /app/packages/shared /app/packages/bridge
CMD ["mc-bridge"]
```

The server image includes the pre-built frontend as static files, served directly by FastAPI (via Starlette's `StaticFiles`). No separate frontend container or CDN is needed for v1.

---

## Testing

### Strategy

Tests are organized in three tiers, run in order of speed:

| Tier | Scope | Tool | Runtime | Runs On |
|------|-------|------|---------|---------|
| Unit | Business logic, schema validation, session mapping, credential masking | pytest | Seconds | Every commit (pre-commit hook) |
| Integration | API routes with test DB, SSE streaming, WebSocket, RLS enforcement | pytest + httpx + testcontainers | ~1–2 min | Every push (CI) |
| E2E | Full user flows: login → create project → assign task → chat → complete | Playwright | ~3–5 min | Every push to main (CI) |

### Python Tests (Server + Bridge)

```bash
# Run all Python tests
uv run pytest

# Run only server tests
uv run pytest packages/server/tests

# Run only bridge tests
uv run pytest packages/bridge/tests

# Run only shared tests
uv run pytest packages/shared/tests
```

**Integration tests use testcontainers** to spin up a real PostgreSQL instance per test session. This ensures:

- RLS policies are tested against real PostgreSQL (not mocked).
- Migration correctness is validated (Alembic runs against the test DB).
- Full-text search uses real `tsvector` indexing.

**Bridge tests mock the Mission Control API and the OpenClaw Gateway.** The Bridge's behavior is tested in isolation:

- SSE reconnection: mock SSE server that drops connections at controlled intervals.
- Message relay: mock MC API for outbound posts, mock Gateway for inbound delivery.
- Session mapping: real SQLite (in-memory) for state persistence tests.
- Credential loading: mock environment and secrets file.

### Frontend Tests

```bash
cd frontend
npm run test               # Vitest unit + component tests
npm run test:e2e           # Playwright E2E tests
```

**Component tests** validate Kanban board state updates from mock SSE events, chat message rendering, search result display, and org switching.

**E2E tests** run against a local docker-compose stack (server + postgres + redis + frontend dev server). Key flows covered:

- OIDC login (mocked provider).
- Project creation, lifecycle transitions.
- Task creation, assignment, completion with evidence.
- Chat messaging between two sessions (simulating human + agent).
- Search across projects, tasks, and messages.

### Cross-Component Contract Tests

The shared package includes contract tests that validate the server's actual API responses match the shared Pydantic schemas. These catch drift between what the server returns and what the Bridge expects:

```python
# packages/shared/tests/test_contracts.py

async def test_project_response_matches_schema(mc_client):
    """Server's project response must deserialize into the shared schema."""
    response = await mc_client.get("/api/v1/orgs/test-org/projects")
    for project in response.json()["data"]:
        ProjectResponse.model_validate(project)  # Raises on mismatch
```

These tests import from `shared` but run against a live server instance (via testcontainers), catching schema divergence that unit tests on either side alone would miss.

---

## CI Pipeline

### Workflow: `ci.yml` (runs on every push and PR)

```yaml
name: CI

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy packages/

  test-python:
    runs-on: ubuntu-latest
    needs: lint
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: mc_test
          POSTGRES_USER: mc_test
          POSTGRES_PASSWORD: mc_test
        ports: ["5432:5432"]
      redis:
        image: redis:7
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run pytest --cov=packages/ --cov-report=xml
        env:
          DATABASE_URL: postgresql+asyncpg://mc_test:mc_test@localhost:5432/mc_test
          REDIS_URL: redis://localhost:6379

  test-frontend:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci && npm run test

  e2e:
    runs-on: ubuntu-latest
    needs: [test-python, test-frontend]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: docker compose -f docker/docker-compose.yml up -d
      - run: cd frontend && npm ci && npx playwright install && npm run test:e2e
      - run: docker compose -f docker/docker-compose.yml down
```

Python and frontend tests run in parallel after linting. E2E runs after both pass.

---

## Release and Publishing

### Versioning

Each component has an independent version in its own `pyproject.toml` or `package.json`. Versions follow semver. The shared package version is the compatibility contract — if shared bumps a major version, both server and Bridge must update before release.

A version compatibility matrix is maintained in `packages/shared/openclaw_mc_shared/version.py`:

```python
# Minimum shared version required by each component
SERVER_REQUIRES_SHARED = ">=0.1.0,<1.0.0"
BRIDGE_REQUIRES_SHARED = ">=0.1.0,<1.0.0"

# API version (reported in X-MC-API-Version header)
API_VERSION = "2026.1"
```

### Release Triggers

Releases are triggered by **git tags**, not branch pushes. This separates CI (every push) from release (intentional act).

| Tag Pattern | Triggers | Artifact |
|-------------|----------|----------|
| `server-v*` (e.g., `server-v0.2.0`) | `release-server.yml` | Docker image → GitHub Container Registry |
| `bridge-v*` (e.g., `bridge-v0.1.3`) | `release-bridge.yml` | Python package → PyPI |
| `frontend-v*` (e.g., `frontend-v0.3.0`) | `release-frontend.yml` | Built into next server image |

### Server Release

```yaml
# .github/workflows/release-server.yml
name: Release Server

on:
  push:
    tags: ["server-v*"]

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci && npm run build
      - uses: docker/build-push-action@v5
        with:
          file: docker/server.Dockerfile
          push: true
          tags: ghcr.io/openclaw/mission-control:${{ github.ref_name }}
```

The server image is pushed to GitHub Container Registry (GHCR). Self-hosted users pull from GHCR. The hosted deployment is updated via the deploy workflow.

### Bridge Release

```yaml
# .github/workflows/release-bridge.yml
name: Release Bridge

on:
  push:
    tags: ["bridge-v*"]

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv build packages/shared
      - run: uv build packages/bridge
      - run: uv publish packages/shared/dist/* packages/bridge/dist/*
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}
```

The Bridge is published to PyPI as `openclaw-mc-bridge`, which depends on `openclaw-mc-shared`. Users install via:

```bash
pip install openclaw-mc-bridge
```

Or update via:

```bash
openclaw update                        # preferred
pip install --upgrade openclaw-mc-bridge   # manual
```

Both `shared` and `bridge` are published in the same release action to ensure version consistency.

### Hosted Deployment

```yaml
# .github/workflows/deploy.yml
name: Deploy Hosted

on:
  workflow_dispatch:                    # manual trigger
  workflow_run:                        # or after server release
    workflows: ["Release Server"]
    types: [completed]

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch' }}
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Lightsail
        run: |
          # Pull new image on Lightsail instance
          # Run Alembic migrations
          # Restart containers with zero-downtime rolling update
```

Migrations run before the new server version starts, ensuring the database schema is ready.

---

## Local Development Workflow

### First-Time Setup

```bash
git clone https://github.com/openclaw/mission-control.git
cd mission-control

# Backend
uv sync                                    # install all Python packages
cp .env.example .env                        # configure local settings
docker compose -f docker/docker-compose.dev.yml up -d postgres redis  # start deps
uv run alembic upgrade head                 # run migrations

# Frontend
cd frontend && npm install && cd ..

# Start everything
uv run uvicorn app.main:app --reload        # server with hot reload
cd frontend && npm run dev                  # Vite HMR
uv run mc-bridge                            # bridge (optional, for integration testing)
```

### Day-to-Day

```bash
uv run pytest                              # run tests
uv run ruff check . --fix                  # lint + autofix
uv run mypy packages/                      # type check
cd frontend && npm run test                # frontend tests
```

### Working on the Bridge

The Bridge can be developed and tested independently of a running Mission Control server. Bridge tests mock the MC API, so no server instance is needed. For integration testing against a real server:

```bash
docker compose -f docker/docker-compose.dev.yml up    # starts server + deps
uv run mc-bridge                                        # bridge connects to local server
```

---

## Summary

| Concern | Decision |
|---------|----------|
| Repo structure | Monorepo, uv workspaces (Python), npm (frontend) |
| Shared code | `openclaw-mc-shared` package (Pydantic schemas, event types, constants) |
| Server artifact | Docker image → GHCR |
| Bridge artifact | Python package → PyPI |
| Frontend artifact | Built static files bundled into server Docker image |
| Testing | Unit (pytest/Vitest) → Integration (testcontainers) → E2E (Playwright) |
| Contract testing | Shared schema validation against live server responses |
| CI | GitHub Actions on every push; lint → test → e2e |
| Release | Git tag per component; independent versioning |
| Local dev | uv sync + docker-compose dev profile + hot reload |
