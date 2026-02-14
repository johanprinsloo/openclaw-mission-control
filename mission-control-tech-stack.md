# Mission Control Tech Stack

This document defines the technology choices for Mission Control, covering server, frontend, database, infrastructure, and tooling. Choices are grounded in the requirements defined in the product plan, API design, and persistence strategy.

## Decision Criteria

Selections prioritize, in order:

1. **Fitness for requirements** — SSE, WebSocket, PostgreSQL RLS, multi-tenancy, full-text search.
2. **Developer experience** — Fast iteration, good debugging, low boilerplate.
3. **Open-source contributor accessibility** — Common languages and frameworks with large communities.
4. **Operational simplicity** — Minimal infrastructure components, easy to self-host.
5. **Performance** — Sufficient for the expected workload (I/O-bound API serving, real-time streaming).

---

## Server

### Framework: FastAPI (Python 3.12+)

**Why FastAPI:**

- **Async-native.** The system is I/O-bound (database queries, SSE streaming, WebSocket relay). FastAPI's ASGI foundation (Starlette) handles thousands of concurrent connections efficiently without threads.
- **SSE support.** Starlette's `StreamingResponse` provides native SSE with no additional dependencies. Each SSE connection is a lightweight async generator.
- **WebSocket support.** Built into Starlette. WebSocket chat connections are first-class, with per-connection lifecycle management.
- **Automatic OpenAPI spec.** FastAPI generates an OpenAPI 3.1 spec from route definitions and Pydantic models. This is unusually valuable for Mission Control because agents are primary API consumers — they can use the spec directly for request/response validation.
- **Pydantic for validation.** Request and response models are defined once and enforce type safety at the API boundary. This catches malformed agent requests before they reach business logic.
- **PostgreSQL ecosystem.** Python has the most mature async PostgreSQL libraries (asyncpg for raw performance, SQLAlchemy 2.0 for ORM with async support).
- **Contributor accessibility.** Python is the most widely known language among both web developers and the AI/agent community that Mission Control targets.

**Alternatives considered:**

- *Go (Gin/Echo):* Better raw concurrency for SSE/WebSocket at very high connection counts. But slower development velocity, less expressive data validation, and no automatic OpenAPI generation of comparable quality. Worth revisiting only if SSE connection count exceeds ~10K concurrent per instance.
- *Node.js (Fastify):* Comparable async performance. Weaker PostgreSQL ecosystem (no equivalent to SQLAlchemy). TypeScript adds safety but the overall developer experience for this workload doesn't improve on FastAPI.
- *Rust (Axum):* Best performance, but dramatically slower development and a much smaller contributor pool. Not justified for an I/O-bound system at this scale.

### Key Libraries

| Concern | Library | Notes |
|---------|---------|-------|
| ASGI server | **Uvicorn** | Production ASGI server. Run behind a reverse proxy (Caddy or Nginx). |
| ORM / query builder | **SQLAlchemy 2.0** (async) | Declarative models, relationship management, migration support. Async session via `asyncpg` driver. |
| Migrations | **Alembic** | SQLAlchemy's migration companion. Versioned, auto-generated diffs, CI-tested. |
| Validation | **Pydantic v2** | Request/response models, settings management. Ships with FastAPI. |
| Auth (OIDC) | **Authlib** | OIDC client for GitHub/Google login flows. Mature, well-maintained. |
| Auth (JWT) | **PyJWT** or **python-jose** | Session token issuance and validation for the web UI. |
| Background tasks | **ARQ** (Redis-backed) | Async task queue for data exports, partition management, sub-agent timeout enforcement. Lightweight alternative to Celery. |
| WebSocket management | **Starlette built-in** | Connection registry, per-channel broadcast. Custom thin layer on top for channel subscription logic. |
| Testing | **pytest** + **httpx** (async) | httpx's `AsyncClient` for testing FastAPI routes without starting a server. |
| API key hashing | **passlib** (bcrypt) | Same library for agent API keys and ephemeral sub-agent keys. |

### Project Structure

```
mission-control/
├── alembic/                    # Database migrations
│   └── versions/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── orgs.py         # Organization endpoints
│   │       ├── users.py        # User endpoints
│   │       ├── projects.py     # Project endpoints
│   │       ├── tasks.py        # Task endpoints
│   │       ├── channels.py     # Channel + message endpoints
│   │       ├── sub_agents.py   # Sub-agent endpoints
│   │       ├── events.py       # Event log + SSE stream
│   │       ├── search.py       # Unified search endpoint
│   │       ├── exports.py      # Data export endpoints
│   │       └── subscriptions.py
│   ├── auth/
│   │   ├── oidc.py             # OIDC login/callback flows
│   │   ├── api_key.py          # API key validation
│   │   └── dependencies.py     # FastAPI dependency injection for auth
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── services/               # Business logic (transitions, dependency checks, etc.)
│   ├── realtime/
│   │   ├── sse.py              # SSE connection manager and event dispatch
│   │   └── ws.py               # WebSocket connection manager and channel broadcast
│   ├── core/
│   │   ├── config.py           # Settings (Pydantic BaseSettings, env-driven)
│   │   ├── database.py         # Async engine, session factory, RLS setup
│   │   ├── security.py         # Hashing, token generation
│   │   └── middleware.py       # Org resolution, request logging
│   └── main.py                 # App factory, router mounting, lifespan events
├── tests/
│   ├── api/                    # Route-level integration tests
│   ├── services/               # Business logic unit tests
│   └── conftest.py             # Fixtures: test DB, test client, factory functions
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml      # Local dev: app + postgres + redis
├── .env.example
├── pyproject.toml
└── README.md
```

### RLS Integration Pattern

The database session middleware sets the org context on every request:

```python
@app.middleware("http")
async def set_org_context(request: Request, call_next):
    org_id = request.state.org_id  # resolved from route + auth
    async with get_session() as session:
        await session.execute(
            text("SET app.current_org_id = :org_id"),
            {"org_id": str(org_id)}
        )
        request.state.db = session
        response = await call_next(request)
    return response
```

Platform-level routes (org listing, auth) bypass this middleware and use sessions without RLS context.

---

## Frontend

### Framework: Vue 3 (Composition API) + TypeScript

**Why Vue 3:**

- **Composition API** aligns well with the real-time data patterns needed (SSE event handlers, WebSocket message streams, reactive Kanban state).
- **Single-file components** keep template, logic, and scoped styles colocated — good for the mix of UI types (boards, forms, chat).
- **Smaller bundle size** than React for a comparable feature set, which matters for the self-hosted deployment where users may be on modest infrastructure.
- **TypeScript support** is mature in Vue 3 and provides type safety across API response handling.

**Why TypeScript:** The API returns well-defined JSON shapes (documented in the OpenAPI spec). TypeScript interfaces generated from the spec catch integration errors at build time rather than runtime. This is especially valuable for the real-time paths where malformed event handling bugs are hard to reproduce.

### Key Libraries

| Concern | Library | Notes |
|---------|---------|-------|
| Build tool | **Vite** | Fast HMR, Vue-native, handles TypeScript and CSS. |
| State management | **Pinia** | Vue 3's recommended store. One store per domain: projects, tasks, channels, auth. |
| Router | **Vue Router 4** | Org-scoped route structure: `/orgs/:slug/projects`, etc. |
| HTTP client | **ky** or **ofetch** | Lightweight fetch wrappers. Auto-attach auth cookies/headers. Types generated from OpenAPI spec. |
| Real-time (SSE) | **EventSource API** (native) | No library needed. Wrapping composable handles reconnection and subscription filtering. |
| Real-time (WebSocket) | **Composable wrapper** | Thin wrapper over native WebSocket with auto-reconnect, exponential backoff, and channel multiplexing. |
| UI components | **Headless UI** or **Radix Vue** | Unstyled, accessible primitives (dialogs, dropdowns, menus). Styled with Tailwind. |
| Styling | **Tailwind CSS** | Utility-first. Consistent design without a heavy component library. |
| Kanban drag-and-drop | **vuedraggable** (SortableJS) | Drag-and-drop for project board (lifecycle lanes) and task board (status columns). |
| Chat UI | **Custom components** | Chat is simple enough (message list + input + mentions) that a library adds more weight than value. |
| Date/time | **date-fns** | Lightweight, tree-shakeable. Used for relative timestamps in event log and chat. |
| Testing | **Vitest** + **Vue Test Utils** | Unit and component tests. Vitest is Vite-native and fast. |
| E2E testing | **Playwright** | Cross-browser E2E tests covering critical flows (login, task transitions, chat). |

### Frontend Structure

```
frontend/
├── src/
│   ├── api/                    # Generated types + API client functions
│   │   ├── types.ts            # Generated from OpenAPI spec
│   │   └── client.ts           # Typed fetch wrappers per resource
│   ├── composables/            # Shared reactive logic
│   │   ├── useSSE.ts           # SSE connection + event dispatch
│   │   ├── useWebSocket.ts     # WebSocket connection + channel multiplexing
│   │   ├── useAuth.ts          # Login state, org switching
│   │   └── useSearch.ts        # Debounced search with type filtering
│   ├── stores/                 # Pinia stores
│   │   ├── auth.ts
│   │   ├── projects.ts
│   │   ├── tasks.ts
│   │   ├── channels.ts
│   │   └── events.ts
│   ├── views/                  # Route-level page components
│   │   ├── ProjectBoard.vue
│   │   ├── TaskBoard.vue
│   │   ├── ChannelView.vue
│   │   ├── EventLog.vue
│   │   ├── OrgSettings.vue
│   │   └── Search.vue
│   ├── components/             # Reusable UI components
│   │   ├── kanban/
│   │   ├── chat/
│   │   └── common/
│   ├── layouts/
│   │   └── OrgLayout.vue       # Sidebar nav, org switcher, notification tray
│   ├── router/
│   │   └── index.ts
│   └── main.ts
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

### Real-Time Data Flow

```
                    ┌──────────────┐
                    │  FastAPI     │
                    │  Server      │
                    ├──────┬───────┤
                    │ SSE  │  WS   │
                    └──┬───┴───┬───┘
                       │       │
            ┌──────────┘       └──────────┐
            ▼                             ▼
    ┌───────────────┐           ┌─────────────────┐
    │ useSSE()      │           │ useWebSocket()   │
    │ composable    │           │ composable       │
    └───────┬───────┘           └────────┬─────────┘
            │                            │
            ▼                            ▼
    ┌───────────────┐           ┌─────────────────┐
    │ Pinia stores  │           │ Channel store    │
    │ (projects,    │           │ (messages,       │
    │  tasks,       │           │  typing status)  │
    │  events)      │           │                  │
    └───────┬───────┘           └────────┬─────────┘
            │                            │
            ▼                            ▼
    ┌───────────────┐           ┌─────────────────┐
    │ Kanban boards │           │ Chat UI          │
    │ Event log     │           │                  │
    │ Notifications │           │                  │
    └───────────────┘           └─────────────────┘
```

SSE events update Pinia stores, which reactively update all subscribed components. No polling.

---

## Database

### PostgreSQL 16+

As defined in the persistence strategy. Version 16 is specified for:

- Mature declarative partitioning with partition pruning optimizations.
- Generated columns (used for `search_vector` tsvector fields).
- Row Level Security performance improvements.
- `pg_stat_io` for monitoring I/O patterns in production.

### Connection: asyncpg

Direct async PostgreSQL driver (no libpq dependency). Used by SQLAlchemy's async engine. Provides binary protocol for faster data transfer than text-based drivers.

### Connection Pooling

Application-level pooling via SQLAlchemy's async pool (backed by asyncpg) for development and low-traffic self-hosted deployments. PgBouncer in transaction mode for the hosted offering when connection count exceeds what a single PostgreSQL instance can handle.

---

## Background Task Queue

### ARQ (Redis-backed)

Lightweight async task queue for:

- **Data exports:** Generating full org exports asynchronously.
- **Partition management:** Creating upcoming monthly partitions, detaching and archiving old partitions.
- **Sub-agent timeout enforcement:** Checking for expired sub-agents and revoking their keys.
- **Search index maintenance:** Reindexing after bulk operations (if needed in future).
- **Notification delivery:** Sending external notifications (email, Signal) without blocking API responses.

ARQ is chosen over Celery for its async-native design (no sync worker overhead), simpler configuration, and smaller footprint. Redis is the only additional infrastructure dependency it introduces.

### Redis

Used exclusively for:

- ARQ task queue (job scheduling and results).
- WebSocket channel broadcast (pub/sub for multi-process deployments where a single in-memory registry is insufficient).
- Session store for OIDC JWT revocation (short-lived key-value lookups).

Redis is **not** used for caching application data in v1. PostgreSQL query performance with proper indexing is sufficient. Caching can be added later if needed without architectural changes.

---

## Infrastructure

### Deployment Target: AWS Lightsail

Lightsail provides fixed-cost instances with predictable pricing, appropriate for both the initial hosted offering and as a recommended self-hosted target.

### Container Strategy

The application is packaged as Docker containers for consistent deployment across environments.

```
docker-compose.yml (production)
├── app           # FastAPI (Uvicorn, 4 workers)
├── worker        # ARQ worker (background tasks)
├── postgres      # PostgreSQL 16 (or external RDS)
├── redis         # Redis 7 (queue + pub/sub)
└── caddy         # Reverse proxy, automatic TLS
```

**Caddy** is chosen as the reverse proxy over Nginx for:

- Automatic HTTPS via Let's Encrypt with zero configuration.
- Native WebSocket and SSE proxying without extra directives.
- Simple Caddyfile configuration (important for self-hosted users customizing their setup).

### Self-Hosted Deployment

Self-hosted users run the same `docker-compose.yml` on their own infrastructure. The only difference is configuration:

- `DEPLOYMENT_MODE=single-tenant`
- Database connection string pointing to their PostgreSQL instance (or the bundled container).
- OIDC provider credentials (or disabled, with local username/password fallback for isolated environments).

A one-line install script is provided:

```bash
curl -sSL https://get.openclaw.dev/mission-control | bash
```

This pulls the Docker images, generates a `.env` file from interactive prompts, and starts the stack.

### Hosted Offering

The hosted deployment adds:

- **RDS PostgreSQL** (instead of containerized PostgreSQL) for managed backups, PITR, and failover.
- **ElastiCache Redis** for managed Redis.
- **S3** for data export storage and cold-tier message/event archives.
- **GitHub Actions CI/CD** deploying to Lightsail container service on merge to main.

### Monitoring and Observability

| Concern | Tool | Notes |
|---------|------|-------|
| Structured logging | **structlog** | JSON-formatted logs with request ID, org ID, user ID context. |
| Metrics | **Prometheus** (via `starlette-exporter`) | Request latency, SSE connection count, WebSocket connection count, queue depth. |
| Alerting | **Grafana** or Lightsail alarms | Threshold alerts on error rate, queue backlog, connection saturation. |
| Error tracking | **Sentry** (optional) | Exception capture with org/user context. Recommended for hosted; optional for self-hosted. |
| Health checks | `GET /health` and `GET /ready` | Liveness (app responding) and readiness (DB + Redis connected) probes. |

---

## Development Tooling

| Concern | Tool | Notes |
|---------|------|-------|
| Python version management | **uv** | Fast dependency resolution and virtual environment management. Replaces pip + venv + pip-tools. |
| Linting / formatting | **Ruff** | Single tool for linting and formatting. Replaces flake8 + black + isort. |
| Type checking | **mypy** (strict mode) | Catches type errors in business logic and ORM queries. |
| Pre-commit hooks | **pre-commit** | Runs Ruff, mypy, and test subset before every commit. |
| Frontend linting | **ESLint** + **Prettier** | Standard Vue/TypeScript configuration. |
| API spec generation | **FastAPI auto-export** | OpenAPI JSON exported on build; frontend types generated from it via `openapi-typescript`. |
| Local development | **docker-compose** (dev profile) | Hot-reload for both FastAPI (Uvicorn --reload) and Vite (HMR). PostgreSQL and Redis run in containers. |
| CI | **GitHub Actions** | Lint → type check → test (pytest + Vitest) → build → deploy (on main). |

---

## Summary

| Layer | Choice | Key Rationale |
|-------|--------|---------------|
| Server framework | FastAPI (Python 3.12+) | Async SSE/WS, OpenAPI generation, PostgreSQL ecosystem |
| ORM | SQLAlchemy 2.0 (async) | Mature, migration support via Alembic, RLS-compatible |
| Database | PostgreSQL 16+ | Relational fit, RLS, partitioning, FTS |
| Task queue | ARQ + Redis | Async-native, lightweight, minimal config |
| Frontend framework | Vue 3 + TypeScript | Composition API for real-time, SFC productivity |
| Build tool | Vite | Fast HMR, Vue-native |
| Styling | Tailwind CSS | Utility-first, no heavy UI framework |
| Reverse proxy | Caddy | Auto-TLS, simple config, native WS/SSE support |
| Containers | Docker + docker-compose | Consistent across hosted and self-hosted |
| CI/CD | GitHub Actions | Native to the repo hosting platform |
| Monitoring | structlog + Prometheus + Grafana | Structured logs, metric dashboards, alerting |
