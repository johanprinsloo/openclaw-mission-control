# Mission Control Implementation Plan

This document defines the step-by-step implementation plan for Mission Control. Each phase has clear goals, acceptance criteria, and references to the spec documents. Every step is scoped to be implementable and testable independently.

## Plan Structure

The plan is organized into five stages:

1. **POC (Phases 1–6):** Validate low-confidence components in isolation before committing to full implementation.
2. **Foundation (Phases 7–10):** Build the core infrastructure that all features depend on.
3. **Dogfood Core (Phases 11–16):** Build the minimum feature set needed to manage work through Mission Control itself: Orgs, Users, Projects, Tasks, Channels, and the Comms Bridge. This stage ends with a **Dogfood Gate** — Mission Control is deployed and used to coordinate all subsequent development.
4. **Remaining Features (Phases 17–21):** Build the remaining product features, now managed and tracked through Mission Control. Agents working on these phases communicate through MC channels and report status through MC tasks.
5. **Release (Phase 22):** Production deployment, self-hosting, and release pipelines.

Each phase produces a working, testable artifact. Phases within a stage are sequential (each builds on the previous), but some phases across stages can overlap where noted.

### Why Dogfood Early

The Comms Bridge is the highest-risk integration point in the system. Deferring it to the end (as a typical integration phase) means the first real test of agent-to-MC communication happens late, when changes are expensive. Moving it to Stage 3 provides two benefits:

1. **Extended real-world testing.** The Bridge runs under sustained load for the entire duration of Stages 4 and 5, surfacing reliability issues (reconnection edge cases, session mapping bugs, memory leaks) that short test runs cannot.
2. **Self-hosted validation.** The development team (humans and agents) operates as the first real tenant — validating multi-user workflows, notification routing, task lifecycle, and chat in a way that synthetic tests cannot replicate.

---

## Reference Documents

| Short Name | Document |
|------------|----------|
| **PRODUCT** | Product Plan (Openclaw Mission Control) |
| **API** | Mission Control API Design |
| **PERSIST** | Data Persistence Strategy |
| **STACK** | Tech Stack Selection |
| **BRIDGE** | Comms Bridge Plugin Spec |
| **SECURITY** | Security Stance |
| **FRONTEND** | Frontend Architecture |
| **STRUCTURE** | Project Structure and Build Pipeline |
| **STYLE** | UI Style & Design Guide |

---

# Stage 1: Proof of Concept

Validate the six low-confidence components. Each POC is a standalone mini-project within the monorepo under the `poc/` directory (e.g., `poc/rls/`, `poc/sse/`, `poc/websocket/`). POC code is checked into the repository so it can be referenced during production implementation — but it is not production code and is not imported by production packages. Each POC produces a `RESULTS.md` documenting findings, performance measurements, and any spec changes needed. Lessons from each POC inform the Foundation phase.

---

## Phase 1: RLS Tenant Isolation

**Goal:** Prove that PostgreSQL Row Level Security reliably isolates tenant data with the session-variable pattern, and measure the performance overhead.

**References:** PERSIST §Tenant Isolation, SECURITY §Principles

### Deliverables

1. A minimal PostgreSQL schema with 3 tables: `organizations`, `projects`, `tasks`. Both `projects` and `tasks` have an `org_id` column.
2. RLS policies on `projects` and `tasks` using `current_setting('app.current_org_id')`.
3. A Python test script (asyncpg, no ORM) that:
   - Creates two orgs with seed data (10 projects, 100 tasks each).
   - Sets the session variable to Org A's ID and queries projects — asserts only Org A's data is returned.
   - Sets the session variable to Org B's ID and queries projects — asserts only Org B's data is returned.
   - Attempts to query Org A's data while set to Org B — asserts zero rows returned.
   - Attempts to INSERT a project with Org A's ID while set to Org B — asserts failure.
   - Attempts to UPDATE/DELETE Org A's data while set to Org B — asserts failure.
4. A performance benchmark: run the same query set with and without RLS enabled, measure latency difference across 1,000 iterations.

### Acceptance Criteria

- [ ] All cross-tenant access attempts return zero rows or fail.
- [ ] INSERT with wrong org_id is rejected by RLS policy.
- [ ] UPDATE/DELETE across tenants is rejected by RLS policy.
- [ ] RLS latency overhead is < 5% on indexed queries.
- [ ] Results documented in `poc/rls/RESULTS.md`.

### Risks Being Validated

- Does the `SET` session variable approach work reliably with connection pooling?
- Does RLS add measurable overhead on indexed lookups?
- Are there edge cases with JOINs across RLS-protected tables?

---

## Phase 2: SSE Event Streaming

**Goal:** Prove that FastAPI/Starlette can sustain hundreds of concurrent SSE connections with subscription-based event filtering and Last-Event-ID replay.

**References:** API §Real-Time Communication (SSE), FRONTEND §Real-Time Data Flow (SSE)

### Deliverables

1. A minimal FastAPI app with:
   - `POST /events` — accepts a JSON event payload and broadcasts it to subscribers.
   - `GET /events/stream` — SSE endpoint that streams events to the client.
   - `PUT /subscriptions` — sets topic filters for the calling client.
2. An in-memory event buffer (last 1,000 events) supporting replay from a given event ID.
3. Subscription filtering: the SSE stream only delivers events matching the client's subscriptions.
4. A load test script that:
   - Opens 200 concurrent SSE connections, each subscribed to different topics.
   - Posts 1,000 events across 10 topics.
   - Asserts each connection received only its subscribed events.
   - Disconnects 50 clients, posts 100 more events, reconnects them with `Last-Event-ID`, and asserts they receive the missed events.
5. Memory and CPU profiling of the server under sustained 200-connection load.

### Acceptance Criteria

- [ ] 200 concurrent SSE connections sustained for 5 minutes without errors.
- [ ] Subscription filtering delivers correct events to each client (zero cross-topic leakage).
- [ ] `Last-Event-ID` replay delivers all missed events after reconnection.
- [ ] Memory usage grows linearly with connection count, not exponentially.
- [ ] Server can broadcast 100 events/second to 200 filtered connections.
- [ ] Results documented in `poc/sse/RESULTS.md`.

### Risks Being Validated

- Can Starlette's StreamingResponse handle hundreds of long-lived connections?
- Does the subscription filter add meaningful latency to event dispatch?
- Is the in-memory event buffer sufficient for replay, or do we need Redis/PostgreSQL-backed replay?

---

## Phase 3: WebSocket Chat

**Goal:** Prove that FastAPI/Starlette can handle bidirectional WebSocket chat with channel multiplexing, message ordering, and concurrent senders.

**References:** API §Real-Time Communication (WebSocket), FRONTEND §Real-Time Data Flow (WebSocket)

### Deliverables

1. A minimal FastAPI app with:
   - `WS /channels/ws` — WebSocket endpoint that multiplexes all channels over one connection.
   - `POST /channels/{id}/messages` — REST fallback for posting messages.
   - In-memory channel registry: clients are subscribed to channels on connection.
2. Message ordering: messages posted by different clients to the same channel arrive in consistent order (server-assigned timestamps).
3. REST-to-WebSocket bridge: messages posted via REST are broadcast to WebSocket clients in the channel.
4. A test script that:
   - Opens 50 WebSocket connections, each subscribed to 3 channels (150 channel-subscriptions total).
   - 10 connections concurrently send messages to the same channel.
   - Asserts all 50 connections subscribed to that channel receive all messages in the same order.
   - Posts a message via REST and asserts WebSocket clients receive it.
   - Disconnects and reconnects a client, verifying no duplicate messages.
5. Heartbeat/ping-pong: server sends pings every 30 seconds, client responds, server detects dead connections within 90 seconds.

### Acceptance Criteria

- [ ] 50 concurrent WebSocket connections with channel multiplexing.
- [ ] Messages delivered in consistent order to all subscribers of a channel.
- [ ] REST-posted messages are broadcast to WebSocket clients.
- [ ] Dead connection detected within 90 seconds via missed ping/pong.
- [ ] No message duplication on reconnection.
- [ ] Results documented in `poc/websocket/RESULTS.md`.

### Risks Being Validated

- Does single-connection channel multiplexing work cleanly, or do we need one connection per channel?
- How does message ordering work with concurrent senders across REST and WebSocket?
- What is the memory footprint per WebSocket connection?

---

## Phase 4: Full-Text Search

**Goal:** Prove that PostgreSQL full-text search with generated tsvector columns delivers acceptable search quality and performance across three resource types with unified ranking.

**References:** PERSIST §Full-Text Search Indexes, API §Search

### Deliverables

1. A PostgreSQL schema with `projects`, `tasks`, and `messages` tables, each with generated `search_vector` tsvector columns as specified in PERSIST.
2. GIN indexes on all three search_vector columns.
3. Seed data: 50 projects, 500 tasks, 10,000 messages — with realistic text content (not lorem ipsum).
4. A unified search query that:
   - Searches across all three tables using `ts_rank` for relevance scoring.
   - Returns results in the unified format specified in API §Search (with `resource_type` discriminator).
   - Generates snippets with `ts_headline` and `<mark>` highlighting.
   - Respects access control: given a user's project assignments, filters out messages from channels the user cannot access.
5. Performance benchmarks:
   - Single-term search across 10K messages: target < 50ms.
   - Multi-term search with project filter: target < 50ms.
   - Search with access control filtering (user assigned to 5 of 20 projects): target < 100ms.
6. Search quality assessment: 10 sample queries with expected results, manually verified.

### Acceptance Criteria

- [ ] Unified search returns results from all three resource types, ranked by relevance.
- [ ] Snippet highlighting works with `<mark>` tags.
- [ ] Access control filtering correctly excludes messages from unassigned project channels.
- [ ] Single-term search < 50ms on 10K messages.
- [ ] Weighted search ranks project/task titles higher than message content.
- [ ] Results documented in `poc/search/RESULTS.md`.

### Risks Being Validated

- Is PostgreSQL FTS quality (ranking, stemming) sufficient, or will users find it frustrating?
- Does access control filtering on search results add unacceptable latency?
- Does the UNION-based unified query perform well, or do we need a materialized search view?

---

## Phase 5: Sub-Agent Scoped Credentials

**Goal:** Prove that ephemeral API keys with scoped access (restricted to a specific task and its project channels) can be implemented cleanly within the existing auth model.

**References:** API §Temporary Sub-Agents, SECURITY §API Key Authentication, PRODUCT §Temporary Sub-Agents

### Deliverables

1. A minimal FastAPI app with:
   - `POST /sub-agents` — creates a sub-agent, generates an ephemeral API key, returns it once.
   - Auth middleware that validates ephemeral keys and enforces scope (only the assigned task and its project channels are accessible).
   - `POST /sub-agents/{id}/terminate` — revokes the ephemeral key immediately.
2. The ephemeral key is bcrypt-hashed in the database. The full key is returned only on creation.
3. Scope enforcement tests:
   - Sub-agent can `GET /tasks/{assignedTaskId}` — succeeds.
   - Sub-agent can `POST /channels/{assignedProjectChannelId}/messages` — succeeds.
   - Sub-agent can `GET /tasks/{otherTaskId}` — returns 404.
   - Sub-agent can `POST /channels/{otherChannelId}/messages` — returns 404.
   - Sub-agent can `GET /projects` — returns only the assigned task's project(s).
4. Timeout enforcement: sub-agent key expires after `timeout_minutes`. A background task checks for expired sub-agents and revokes their keys.
5. Termination: `POST /terminate` immediately invalidates the key. Subsequent requests return 401.

### Acceptance Criteria

- [ ] Ephemeral key grants access only to the assigned task and its project channel(s).
- [ ] Access to any other resource returns 404 (not 403, per SECURITY).
- [ ] Key is revoked immediately on termination. Subsequent requests fail with 401.
- [ ] Key expires automatically after timeout. Subsequent requests fail with 401.
- [ ] Bcrypt hash stored in DB; plaintext key returned only once on creation.
- [ ] Results documented in `poc/sub-agents/RESULTS.md`.

### Risks Being Validated

- Is per-request scope checking fast enough (key lookup + scope validation on every request)?
- Does scoped access integrate cleanly with RLS (org-level isolation) without conflicts?
- Can the timeout enforcement background task run reliably without missing expired agents?

---

## Phase 6: Comms Bridge ↔ Mission Control Round-Trip

**Goal:** Prove end-to-end message flow between a mock OpenClaw Gateway and Mission Control through the Comms Bridge: SSE event in → session dispatch → agent response → REST post back to channel.

**References:** BRIDGE §Message Flow, BRIDGE §Session Mapping, BRIDGE §Command Flow

### Deliverables

1. A minimal Mission Control server (from Phase 2 SSE + Phase 3 WebSocket POCs combined) with:
   - Channels, messages, and SSE streaming.
   - API key auth for the agent.
2. A minimal mock OpenClaw Gateway with:
   - An HTTP endpoint that accepts messages and returns a canned agent response.
   - A command endpoint that accepts `/status` and returns a canned status string.
3. A minimal Comms Bridge implementation that:
   - Connects to Mission Control via SSE.
   - Receives a `message.created` event for a channel the agent is subscribed to.
   - Translates the message and delivers it to the mock Gateway.
   - Receives the Gateway's response and posts it back to the Mission Control channel via REST.
   - Receives a `command.invoked` event, routes `/status` to the Gateway, and posts the output back.
4. Session mapping: the Bridge creates an OpenClaw session key from the channel ID and maintains it in SQLite.
5. A test script that:
   - Posts a message to a Mission Control channel (simulating a human user).
   - Asserts the Bridge delivers it to the Gateway.
   - Asserts the Gateway's response appears in the Mission Control channel.
   - Posts `/status` to the channel.
   - Asserts the status output appears in the channel.

### Acceptance Criteria

- [ ] Message posted in MC channel → arrives at mock Gateway within 2 seconds.
- [ ] Gateway response → appears in MC channel within 2 seconds.
- [ ] `/status` command → routed to Gateway → output posted to channel within 3 seconds.
- [ ] Session mapping persisted in SQLite — Bridge restart resumes from last event.
- [ ] SSE reconnection after simulated server restart delivers missed events.
- [ ] Results documented in `poc/bridge/RESULTS.md`.

### Risks Being Validated

- Is the SSE → process → REST round-trip latency acceptable for interactive chat?
- Does the session mapping model work for the Gateway's session semantics?
- Is SQLite reliable enough for Bridge state, or do we need something else?

---

## POC Review Gate

After all six POCs are complete, results are reviewed before proceeding to the Foundation stage. The review assesses:

1. **Feasibility:** Did each POC meet its acceptance criteria?
2. **Architecture changes:** Do any results require changes to the spec documents? (e.g., if RLS overhead is unacceptable, revisit tenant isolation strategy; if PostgreSQL FTS quality is poor, introduce a search engine in v1).
3. **Lessons learned:** What patterns emerged that should be standardized in the Foundation phase?
4. **Risk retirement:** Which risks are fully retired, and which need further validation during Foundation?

The POC code is archived in `poc/` but NOT incorporated into the production codebase. Foundation phase starts fresh with production-grade patterns informed by POC learnings.

---

# Stage 2: Foundation

Build the infrastructure that all features depend on. This stage produces a running (but feature-sparse) application with authentication, database, real-time connections, and CI pipeline.

---

## Phase 7: Repository Scaffolding and CI

**Goal:** Set up the monorepo structure, package configuration, Docker development environment, and CI pipeline so that all subsequent phases start from a working, tested baseline.

**References:** STRUCTURE §Directory Structure, STRUCTURE §CI Pipeline, STACK §Development Tooling

### Deliverables

1. Monorepo structure as specified in STRUCTURE: `packages/server`, `packages/bridge`, `packages/shared`, `frontend/`, `docker/`, `scripts/`, `docs/`.
2. `uv` workspace configuration with all three Python packages.
3. `frontend/` initialized with Vite + Vue 3 + TypeScript + Vuetify + Tailwind + Pinia.
4. `docker-compose.dev.yml` with PostgreSQL 16, Redis 7, and hot-reload configuration for server and frontend.
5. GitHub Actions CI workflow: lint (Ruff + mypy + ESLint) → test (pytest + Vitest) → build.
6. Pre-commit hooks configured (Ruff, mypy).
7. `.env.example` with all configuration variables documented.
8. A health-check endpoint (`GET /health`) that returns 200 when the server starts.

### Acceptance Criteria

- [ ] `uv sync` installs all Python packages without errors.
- [ ] `cd frontend && npm install && npm run dev` starts the Vite dev server.
- [ ] `docker compose -f docker/docker-compose.dev.yml up` starts PostgreSQL + Redis.
- [ ] `uv run pytest` discovers and runs a single placeholder test.
- [ ] `cd frontend && npm run test` discovers and runs a single placeholder test.
- [ ] CI workflow passes on a clean push to main.
- [ ] `GET /health` returns `{"status": "ok"}`.

### Testing Approach

- Verify scaffold by running lint, test, and build steps locally and in CI.
- No business logic to test yet — placeholder tests confirm the pipeline works.

---

## Phase 8: Database Schema and Migrations

**Goal:** Implement the full production database schema with RLS policies, partitioned tables, indexes, and the event immutability trigger. Migrations are managed by Alembic and tested against a real PostgreSQL instance.

**References:** PERSIST §Schema Overview, PERSIST §Indexing Strategy, PERSIST §Event Log Immutability, PERSIST §Tenant Isolation

### Deliverables

1. SQLAlchemy ORM models for all tables defined in PERSIST §Schema Overview.
2. Alembic migration that creates the full schema from scratch.
3. RLS policies on all tenant-scoped tables, as specified in PERSIST §Policy Scope.
4. Partitioned tables for `messages` and `events` with initial partitions (current month + next month).
5. All indexes from PERSIST §Indexing Strategy.
6. Event immutability trigger from PERSIST §Event Log Immutability.
7. Full-text search: generated `search_vector` columns and GIN indexes on `projects`, `tasks`, `messages`.
8. Seed data script: creates a test org, 2 users (human + agent), 3 projects, 10 tasks.

### Acceptance Criteria

- [ ] `alembic upgrade head` creates the full schema on a clean database.
- [ ] `alembic downgrade base` cleanly removes all objects.
- [ ] RLS policies enforce tenant isolation (verified by integration test from POC Phase 1 patterns).
- [ ] Event immutability trigger rejects UPDATE and DELETE on events table.
- [ ] Partitioned tables accept inserts and route to correct partitions.
- [ ] All indexes are created and used by query planner (verified via `EXPLAIN ANALYZE`).
- [ ] Seed data script populates test data successfully.

### Testing Approach

- Integration tests using testcontainers (real PostgreSQL).
- RLS isolation tests: create two orgs, verify cross-tenant access fails.
- Migration round-trip test: `upgrade head` then `downgrade base` then `upgrade head` again.

---

## Phase 9: Authentication and Authorization

**Goal:** Implement OIDC login for humans, API key authentication for agents, JWT session management, CSRF protection, and role-based authorization middleware.

**References:** SECURITY §Authentication Details, SECURITY §CSRF Protection, API §Authentication, PRODUCT §Authorization Model

### Deliverables

1. OIDC login flow: `GET /auth/login`, `GET /auth/callback`, `POST /auth/refresh`, `POST /auth/logout`.
2. JWT session issuance with claims as specified in SECURITY §Session JWT.
3. JWT revocation list in Redis.
4. CSRF double-submit cookie middleware as specified in SECURITY §CSRF Protection.
5. API key validation middleware with O(1) lookup (key prefix hint pattern from SECURITY).
6. Authorization dependency injection: `require_admin`, `require_contributor`, `require_member` FastAPI dependencies.
7. Org-scoping middleware: extracts `orgSlug` from route, resolves org ID, sets RLS session variable.
8. Security headers middleware as specified in SECURITY §Security Headers.
9. CORS configuration as specified in SECURITY §CORS Policy.

### Acceptance Criteria

- [ ] OIDC login with GitHub provider completes successfully (tested with mock OIDC provider in CI).
- [ ] Session JWT issued with correct claims, expires after 1 hour.
- [ ] Revoked JWT is rejected on subsequent requests.
- [ ] CSRF validation rejects POST requests without matching token.
- [ ] CSRF validation skips requests with API key auth (agents).
- [ ] API key authentication succeeds for valid keys, returns 401 for invalid/revoked keys.
- [ ] `require_admin` rejects Contributors with 403.
- [ ] `require_contributor` rejects non-members with 404 (not 403, per SECURITY).
- [ ] RLS session variable set on every org-scoped request.
- [ ] Security headers present on all responses.

### Testing Approach

- Unit tests for JWT creation/validation, CSRF token matching, API key hashing.
- Integration tests with mock OIDC provider (using Authlib's test helpers).
- Authorization matrix test: for each endpoint × role combination, assert correct allow/deny.

---

## Phase 10: Real-Time Infrastructure

**Goal:** Implement production-grade SSE event streaming and WebSocket chat, integrated with the auth and org-scoping middleware from Phase 9.

**References:** API §Real-Time Communication, FRONTEND §Real-Time Data Flow, SECURITY §SSE Connection Authentication, SECURITY §WebSocket Authentication

### Deliverables

1. SSE endpoint: `GET /api/v1/orgs/{orgSlug}/events/stream`. Authenticated, org-scoped, subscription-filtered.
2. Subscription management: `GET/PUT /api/v1/orgs/{orgSlug}/subscriptions`.
3. Event bus: internal pub/sub that routes database events to SSE connections. In-memory for single-process; Redis pub/sub for multi-process.
4. Event buffer for `Last-Event-ID` replay (in-memory, configurable depth).
5. SSE heartbeat: server sends `: heartbeat` comment every 30 seconds.
6. WebSocket endpoint: `WS /api/v1/orgs/{orgSlug}/channels/ws`. Authenticated, org-scoped, channel-multiplexed.
7. WebSocket connection registry: tracks which users are connected to which channels.
8. REST-to-WebSocket bridge: messages posted via REST are broadcast to WebSocket clients.
9. Connection limits per org as specified in SECURITY §Rate Limiting.
10. Auth revocation: SSE sends `session.revoked` event and closes; WebSocket sends close code 4001.

### Acceptance Criteria

- [ ] SSE stream delivers events matching client subscriptions, filtered by org.
- [ ] SSE reconnection with `Last-Event-ID` replays missed events.
- [ ] SSE heartbeat keeps connection alive through proxies.
- [ ] WebSocket delivers chat messages to all channel subscribers.
- [ ] REST-posted messages are broadcast to WebSocket clients.
- [ ] Connection limits enforced: 429 returned when exceeded.
- [ ] Revoked credentials close SSE and WebSocket connections.
- [ ] Multi-process broadcast works via Redis pub/sub.

### Testing Approach

- Integration tests: open SSE/WS connections, post events, assert correct delivery.
- Reconnection test: disconnect client, post events, reconnect with Last-Event-ID, assert replay.
- Load test: 100 concurrent SSE + 50 WS connections, sustained for 2 minutes.
- Auth revocation test: revoke key during active SSE connection, assert connection closes.

---

# Stage 3: Dogfood Core

Build the minimum feature set needed to manage work through Mission Control: Orgs, Users, Projects, Tasks, Channels, and the Comms Bridge. Every phase in this stage delivers both server and frontend, producing a complete vertical slice. At the end of this stage, Mission Control is deployed and used to coordinate all remaining development.

---

## Phase 11: Organizations

**Goal:** Implement org CRUD, org settings, and the org lifecycle (create, active, suspend, delete with grace period).

**References:** API §Organizations, PRODUCT §Organizations, PERSIST §Org Deletion

### Deliverables

**Server:**
1. All org endpoints from API §Organizations: list, create, get, update settings, delete.
2. Org lifecycle state machine: active → suspended → pending_deletion → deleted.
3. Grace period enforcement for deletion (background task via ARQ).
4. Org settings stored as JSONB, validated by Pydantic model from API §Update Org Settings.

**Frontend:**
5. Org selection view (`/orgs`): list orgs the user belongs to, select active org.
6. Org switcher component in the top bar.
7. Org settings view (Admin only): tabbed form for all settings from STYLE §Org Settings.

**Shared:**
8. Org-related Pydantic schemas in `packages/shared`.

### Acceptance Criteria

- [ ] Create org → user becomes Admin → org appears in list.
- [ ] Update org settings → settings persisted and returned on get.
- [ ] Delete org → grace period starts → org is read-only → after grace period, data deleted.
- [ ] Non-member access to org returns 404.
- [ ] Org switcher updates active org context and reloads data.
- [ ] Settings view renders all tabs, saves successfully.

### Testing Approach

- API integration tests for each endpoint and lifecycle transition.
- Frontend component tests for org switcher and settings form.
- E2E: create org → update settings → verify settings persisted.

---

## Phase 12: Users and API Key Management

**Goal:** Implement user management within orgs: add/remove members, role assignment, agent API key provisioning and rotation.

**References:** API §Users, API §API Key Management, SECURITY §API Key Authentication, PRODUCT §Users

### Deliverables

**Server:**
1. All user endpoints from API §Users: list, add, get, update, remove.
2. API key generation, rotation (with grace period), and revocation from API §API Key Management.
3. Agent user creation returns API key (shown once).

**Frontend:**
4. User management view (Admin only): table with AG Grid showing members, roles, actions.
5. "Invite User" dialog: human (email) or agent (identifier) flow.
6. API key rotation dialog: confirmation, new key display (copy-to-clipboard), grace period info.

**Shared:**
7. User-related Pydantic schemas in `packages/shared`.

### Acceptance Criteria

- [ ] Add human user → user can log in and access org.
- [ ] Add agent user → API key returned once → agent can authenticate.
- [ ] Rotate API key → old key works during grace period → old key stops working after grace period.
- [ ] Revoke API key → immediate 401 on subsequent requests.
- [ ] Remove user from org → user can no longer access org resources.
- [ ] Role change (Contributor → Admin) → user gains admin permissions immediately.

### Testing Approach

- API integration tests for each endpoint, including grace period timing.
- Frontend component tests for user table, invite dialog, key rotation dialog.
- E2E: add agent → authenticate with key → rotate key → verify old key expires.

---

## Phase 13: Projects

**Goal:** Implement project CRUD, lifecycle transitions, and the Kanban project board.

**References:** API §Projects, PRODUCT §Projects, FRONTEND §Project Board, STYLE §Kanban Cards

### Deliverables

**Server:**
1. All project endpoints from API §Projects: list, create, get, update, transition, delete (end-of-life).
2. Lifecycle transition validation: ordered stages with backward transition support.
3. Project creation auto-creates a default project channel.
4. Transition events emitted to SSE.

**Frontend:**
5. Project Board view: Kanban columns by lifecycle stage, drag-and-drop to transition.
6. Project cards styled per STYLE §Kanban Cards (name, owner, task count, type badge, left border color).
7. Create Project dialog (Admin only).
8. Project Detail view (slide-over panel): metadata, links, assigned users, task summary.
9. SSE integration: board updates in real-time when projects are created or transitioned.

### Acceptance Criteria

- [ ] Create project → appears in Definition column.
- [ ] Drag project to Development → transition confirmed, card moves with animation.
- [ ] Invalid transition (Definition → Maintenance) → drag rejected with tooltip.
- [ ] Backward transition (Testing → Development) → succeeds.
- [ ] End-of-life project (Admin) → project removed from board.
- [ ] SSE: another user transitions a project → board updates in real-time.

### Testing Approach

- API integration tests for lifecycle state machine (all valid/invalid transitions).
- Frontend component tests for Kanban board rendering, drag-and-drop transitions.
- E2E: create project → transition through stages → end-of-life → verify board state.

---

## Phase 14: Tasks

**Goal:** Implement task CRUD, status transitions, dependencies, evidence, and the Kanban task board.

**References:** API §Tasks, API §Dependencies, PRODUCT §Tasks, FRONTEND §Task Board, STYLE §Kanban Cards

### Deliverables

**Server:**
1. All task endpoints from API §Tasks: list, create, get, update, transition.
2. Dependency endpoints: add, remove, circular dependency detection.
3. Evidence validation on completion transition.
4. Task transition events emitted to SSE.
5. Task filters: by project, status, assignee, priority.

**Frontend:**
6. Task Board view: Kanban columns by status, drag-and-drop to transition.
7. Task cards styled per STYLE (title, priority, assignee, project badges, dependency icon).
8. Create Task dialog.
9. Task Detail view (slide-over): full metadata, dependencies, evidence, assigned users.
10. Evidence submission modal (triggered when dragging to Complete with evidence required).
11. Filter bar: project, assignee, priority, "My Tasks" toggle.
12. Task list view (AG Grid alternate): sortable, filterable table.
13. SSE integration: board updates in real-time.

### Acceptance Criteria

- [ ] Create task with project and assignee → appears in Backlog column.
- [ ] Drag to Complete with evidence required → evidence modal opens → submit → card moves.
- [ ] Drag to Complete without required evidence → transition rejected with error message.
- [ ] Add dependency → blocked task shows dependency icon → cannot transition to Complete until blocker is Complete.
- [ ] Circular dependency → returns 409 Conflict.
- [ ] Filters narrow visible tasks correctly.
- [ ] AG Grid view shows same data as Kanban board with sorting and column filtering.
- [ ] SSE: task transitioned by agent → board updates in real-time.

### Testing Approach

- API integration tests: lifecycle transitions, evidence validation, dependency graph (including circular detection).
- Frontend component tests: Kanban board, filter bar, evidence modal.
- E2E: create task → assign → transition through statuses with evidence → verify completion.

---

## Phase 15: Channels and Chat

**Goal:** Implement channel listing, message posting, chat UI, and real-time message delivery via WebSocket.

**References:** API §Channels, FRONTEND §Channel View, STYLE §interaction patterns

### Deliverables

**Server:**
1. All channel endpoints from API §Channels: list, get details, list messages, post message.
2. Mention parsing: extract user IDs from `mentions` array, trigger notification events.
3. OpenClaw command detection: messages starting with `/` emit `command.invoked` event.
4. Message pagination (newest first, cursor-based).

**Frontend:**
5. Channel list in sidebar: org-wide channels and project channels (grouped by project).
6. Channel View: message list, message input, mention autocomplete, command autocomplete.
7. Message rendering: human/agent distinction (agent badge), timestamps, mention highlighting.
8. Typing indicators (WebSocket frame type).
9. WebSocket integration: real-time message delivery.
10. Offline message queuing: messages typed while disconnected are queued and sent on reconnection.
11. Scroll-to-load history (paginated via REST).
12. Unread indicators on channel list items.

### Acceptance Criteria

- [ ] Post message via UI → appears for all channel subscribers via WebSocket.
- [ ] Post message via REST (agent) → appears for WebSocket-connected users.
- [ ] Mention @user → user receives notification event.
- [ ] `/status` message → `command.invoked` event emitted.
- [ ] Typing indicator appears when another user is composing.
- [ ] Disconnect WebSocket → type message → reconnect → message delivered.
- [ ] Scroll to top → older messages loaded from REST.

### Testing Approach

- API integration tests: message posting, pagination, mention parsing.
- Frontend component tests: message rendering, mention autocomplete, typing indicator.
- E2E: two browser sessions, one posts a message → other receives in real-time.

---


## Phase 16: Comms Bridge

**Goal:** Implement the production Comms Bridge plugin, deployed alongside a running Mission Control instance. This is the final phase before dogfooding — once the Bridge works, agents can manage MC work through MC.

**References:** BRIDGE (entire document), STRUCTURE §packages/bridge

### Deliverables

1. Full Comms Bridge implementation in `packages/bridge/` with all modules from BRIDGE: SSE listener, message relay, command routing, session mapping, subscription management.
2. Configuration loading from YAML + secrets file.
3. Credential provider abstraction (env, AWS Secrets Manager, Vault).
4. Graceful shutdown sequence from BRIDGE §Updates and Lifecycle Management.
5. Health and metrics endpoint from BRIDGE §Monitoring.
6. Version compatibility check on startup.
7. SQLite local state for session mappings and event cursors.
8. Sub-agent credential relay (basic — sub-agent spawning is Phase 17, but the Bridge must be ready to handle it).

### Acceptance Criteria

- [ ] Bridge connects to MC server, authenticates agent, opens SSE stream.
- [ ] Message in MC channel → delivered to mock Gateway → response posted back to channel.
- [ ] `/status` command → routed to Gateway → output posted to channel.
- [ ] Graceful shutdown → outbound messages flushed, cursors persisted, clean exit.
- [ ] Restart → resumes from last event cursor, no message loss.
- [ ] SSE reconnection after server restart delivers missed events.
- [ ] Health endpoint returns correct connection status.
- [ ] Prometheus metrics exposed for all key counters.
- [ ] Bridge runs stable for 24 hours under continuous event load without memory leaks or connection failures.

### Testing Approach

- Unit tests for each module (SSE parsing, message translation, session mapping, config loading).
- Integration tests with the real MC server (from Phases 11–15) and mock Gateway.
- Reconnection test: restart MC server → verify Bridge reconnects and replays events.
- Shutdown test: send SIGTERM → verify flush and cursor persistence.
- 24-hour soak test: sustained event stream with periodic reconnection, verify memory stable.

---

## Dogfood Gate

After Phase 16, Mission Control is deployed as the coordination system for the remaining development. This is a deliberate transition point, not just a milestone.

### Deployment

1. Deploy Mission Control (server, frontend, Redis, PostgreSQL) to the development environment.
2. Deploy the Comms Bridge on the OpenClaw host alongside the existing agents.
3. Create the "OpenClaw" organization in Mission Control.
4. Register all human contributors and persistent agents as users.
5. Create a "Mission Control" project (stage: Development).
6. Create tasks for all remaining phases (17–22) as MC tasks.
7. Assign agents and humans to tasks.

### Validation Criteria

Before proceeding to Stage 4, verify that the dogfood deployment supports the development workflow:

- [ ] Agents can receive task assignments via the Bridge and SSE.
- [ ] Agents can post status updates to project channels via the Bridge.
- [ ] Humans can view the project board, task board, and chat in the Web UI.
- [ ] Task transitions (Backlog → In-Progress → In-Review → Complete) work end-to-end.
- [ ] At least one task is completed entirely through MC (create → assign → agent works → posts update → submits evidence → completes).

### What Changes

From this point forward:

- All remaining phases are tracked as MC tasks, not just entries in this document.
- Agent sub-tasks, status updates, and blockers are reported in MC project channels.
- The daily development workflow validates MC's core features under real conditions.
- Bugs and issues discovered during dogfooding are filed as MC tasks (Bug type) and prioritized alongside feature work.
- The Bridge runs continuously, accumulating real-world uptime and surfacing reliability issues.

---

# Stage 4: Remaining Features

Build the remaining product features. These phases are managed and tracked through Mission Control itself. Agents working on these phases communicate through MC channels and report status through MC tasks.

**Dogfooding note:** Every bug, edge case, or UX issue discovered while using MC to build these features is a valuable test result. File it as a Bug task in MC and prioritize it. The dogfood experience is as important as the feature work itself.

---

## Phase 17: Sub-Agents

**Goal:** Implement sub-agent spawning, scoped credentials, timeout enforcement, and termination.

**References:** API §Temporary Sub-Agents, PRODUCT §Temporary Sub-Agents, SECURITY §API Key Authentication

### Deliverables

**Server:**
1. All sub-agent endpoints from API §Temporary Sub-Agents: spawn, list, get status, terminate.
2. Ephemeral API key generation with scope enforcement (from POC Phase 5 patterns).
3. Timeout enforcement via ARQ background task.
4. Sub-agent lifecycle events emitted to SSE.
5. Org-level limit enforcement (max concurrent sub-agents from org settings).

**Frontend:**
6. Sub-agent list view: active sub-agents with status, task, creator, time remaining.
7. Spawn sub-agent dialog (from task detail view).
8. Terminate button with confirmation.
9. SSE integration: sub-agent status updates in real-time.

**Bridge:**
10. Update Bridge sub-agent credential relay to work with production sub-agent API.
11. Bridge bootstraps Gateway session for new sub-agents and tears down on termination.

### Acceptance Criteria

- [ ] Spawn sub-agent → ephemeral key returned → key grants scoped access only.
- [ ] Sub-agent can access assigned task and project channel(s) only.
- [ ] Sub-agent access to any other resource returns 404.
- [ ] Timeout → key automatically revoked → requests return 401.
- [ ] Terminate → key immediately revoked.
- [ ] Org limit reached → spawn returns 429.
- [ ] Sub-agent lifecycle events visible in event log.
- [ ] Bridge: sub-agent spawned → Gateway session created → sub-agent communicates via MC channel.
- [ ] Bridge: sub-agent terminated → Gateway session archived.

### Testing Approach

- API integration tests: spawn, scope enforcement, timeout, termination.
- Frontend component tests: sub-agent list, spawn dialog.
- Bridge integration test: spawn sub-agent via MC → verify Bridge bootstraps Gateway session.
- E2E: spawn sub-agent → verify scoped access → terminate → verify key revoked.
- **Dogfood test:** Use a sub-agent via MC to perform a real subtask (e.g., review a PR) during development of subsequent phases.

---

## Phase 18: Event Log

**Goal:** Implement the event log view with filtering, real-time updates, and the project-level audit log.

**References:** API §Event Log, FRONTEND §Event Log, PRODUCT §Event Log

### Deliverables

**Server:**
1. Event log endpoint from API §Event Log: list with filtering by project, task, user, event type, date range.
2. Event types for all state changes (project transitions, task transitions, user changes, messages, sub-agent lifecycle).
3. Event immutability enforced by database trigger (from Phase 8).

**Frontend:**
4. Event Log view: chronological list with filter bar.
5. AG Grid for event display: columns for timestamp, actor, event type, description, project.
6. Filter controls: project, user, type, date range dropdowns.
7. SSE integration: new events appear at top of list in real-time.
8. Per-project audit log: event log filtered to a single project (accessible from project detail view).

### Acceptance Criteria

- [ ] All state-change events are recorded automatically.
- [ ] Filter by project → shows only events for that project.
- [ ] Filter by user → shows only events by that actor.
- [ ] Filter by date range → scoped correctly.
- [ ] SSE: new event → appears at top of list with animation.
- [ ] Project audit log shows only events for the selected project.
- [ ] Events are immutable: UPDATE/DELETE on events table fails.

### Testing Approach

- API integration tests: event recording for each event type, filter combinations.
- Frontend component tests: event list rendering, filter controls.
- E2E: perform actions (create project, transition task) → verify events appear in log.
- **Dogfood test:** Review the event log for the MC project itself — verify that all development activity (task transitions, channel messages, agent actions) is captured accurately.

---

## Phase 19: Search

**Goal:** Implement unified full-text search across projects, tasks, and channel messages.

**References:** API §Search, PERSIST §Full-Text Search Indexes, FRONTEND §Search View

### Deliverables

**Server:**
1. Search endpoint from API §Search: unified query with type filtering, project scoping, date range, pagination.
2. Access-controlled results: messages from unassigned project channels excluded.
3. Snippet generation with `<mark>` highlighting via `ts_headline`.
4. Relevance ranking via `ts_rank` with weighted fields.

**Frontend:**
5. Search input in top bar (debounced, 300ms).
6. Search view: results grouped by resource type, with snippets and highlighting.
7. Filter controls: resource type, project, date range.
8. Click result → navigate to resource detail.

### Acceptance Criteria

- [ ] Search "deploy staging" → returns matching tasks, messages, and projects.
- [ ] Results ranked by relevance (title matches rank higher than description/message content).
- [ ] Snippets show highlighted matching terms.
- [ ] Access control: user not assigned to Project X → messages from Project X's channels excluded.
- [ ] Type filter: search with `types=tasks` → only task results returned.
- [ ] Debounced: no API call until 300ms after user stops typing.

### Testing Approach

- API integration tests: search across resource types, access control, filtering, ranking.
- Frontend component tests: search input debouncing, result rendering, filter controls.
- E2E: create task with known title → search for it → click result → verify navigation.
- **Dogfood test:** Search for real development conversations and tasks in the MC project. Verify that search quality is sufficient for finding past decisions and context.

---

## Phase 20: Data Export

**Goal:** Implement asynchronous org data export.

**References:** API §Data Export, PRODUCT §Data Export

### Deliverables

**Server:**
1. Export endpoints from API §Data Export: request export, check status/download.
2. ARQ background task that generates a JSON export of all org data (projects, tasks, channels, messages, events, users).
3. Export stored in configurable location (local filesystem for self-hosted, S3 for hosted).
4. Export status tracking: pending → processing → ready → expired.

**Frontend:**
5. "Export Data" button in org settings (Admin only).
6. Export status indicator and download link.

### Acceptance Criteria

- [ ] Request export → background task starts → status changes to processing → ready.
- [ ] Download URL returns complete org data as JSON.
- [ ] Export includes all resource types with relationships intact.
- [ ] Non-admin cannot request or download exports.
- [ ] Export expires after configurable duration.

### Testing Approach

- Integration tests: request export, wait for completion, verify content completeness.
- Verify export includes data from all tables, correctly scoped to org.
- **Dogfood test:** Export the MC project's data. Verify it captures the complete development history — projects, tasks, channels, messages, events.

---

## Phase 21: Notifications

**Goal:** Implement the in-app notification system and external notification delivery (email).

**References:** PRODUCT §Notifications and Escalation, FRONTEND §Notification System

### Deliverables

**Server:**
1. Notification event generation for: task assignment, direct mentions, project transitions (to owner).
2. External notification delivery via ARQ: email (using SMTP or a transactional email service).
3. Notification routing respects org-level defaults and user preferences.

**Frontend:**
4. Notification tray in top bar: bell icon, unread count badge, dropdown list.
5. Toast notifications for high-priority events (mentions, task assignments).
6. Notification → click → navigate to relevant resource.

### Acceptance Criteria

- [ ] Task assigned to user → in-app notification appears.
- [ ] @mention in channel → toast notification + tray notification.
- [ ] Email notification sent for mentions (if email configured in org settings).
- [ ] Notification click navigates to the correct resource.
- [ ] Notification tray shows unread count, marks read on click.

### Testing Approach

- Integration tests: trigger notification events, verify they're generated.
- Email delivery test with mock SMTP server.
- Frontend component tests: notification tray rendering, toast display and auto-dismiss.
- E2E: mention user in chat → verify toast appears → click → verify navigation.
- **Dogfood test:** Verify that agents and humans receive timely notifications for task assignments and mentions during normal MC development workflow.

---

# Stage 5: Release

Production deployment, self-hosting, and release pipelines.

---

## Phase 22: Deployment and Self-Hosting

**Goal:** Prepare production deployment configurations, self-hosting guide, and the one-line installer.

**References:** STACK §Infrastructure, STRUCTURE §Release and Publishing, PRODUCT §Deployment & Hosting, PRODUCT §Deployment Modes

### Deliverables

1. Production `docker-compose.yml` (server + worker + redis + caddy).
2. Self-hosted `docker-compose.selfhost.yml` (single-tenant preset with bundled PostgreSQL).
3. Caddy configuration with automatic TLS, WebSocket/SSE proxy, security headers.
4. Self-hosted one-line installer script (`install.sh`): pulls images, generates `.env`, starts stack.
5. Self-hosting guide documentation (`docs/self-hosting-guide.md`).
6. Release workflows from STRUCTURE §Release Triggers: server image → GHCR, bridge → PyPI.
7. Deploy workflow for hosted environment.
8. Deployment mode configuration: `DEPLOYMENT_MODE=single-tenant|multi-tenant`.
9. Smoke test suite: post-deployment health checks for all critical paths.

### Acceptance Criteria

- [ ] `curl -sSL https://get.openclaw.dev/mission-control | bash` produces a running instance.
- [ ] Self-hosted instance: create org, add user, create project, create task, post in channel — all functional.
- [ ] TLS terminates correctly via Caddy.
- [ ] WebSocket and SSE work through the Caddy proxy.
- [ ] Release workflow: push tag → image built → pushed to GHCR / PyPI.
- [ ] Deploy workflow: trigger → migrations run → containers updated → zero-downtime.

### Testing Approach

- Run install script on a clean Ubuntu VM.
- Smoke tests: hit every critical API endpoint after deployment.
- TLS verification: confirm certificate is valid and HSTS header present.
- WebSocket/SSE through proxy: confirm real-time features work.

---

# Phase Summary

| Phase | Stage | Name | Depends On | Estimated Effort |
|-------|-------|------|------------|-----------------|
| 1 | POC | RLS Tenant Isolation | — | Small |
| 2 | POC | SSE Event Streaming | — | Small |
| 3 | POC | WebSocket Chat | — | Small |
| 4 | POC | Full-Text Search | — | Small |
| 5 | POC | Sub-Agent Scoped Credentials | — | Small |
| 6 | POC | Comms Bridge Round-Trip | 2, 3 | Medium |
| — | **Gate** | **POC Review** | 1–6 | — |
| 7 | Foundation | Repo Scaffolding and CI | — | Small |
| 8 | Foundation | Database Schema and Migrations | 7 | Medium |
| 9 | Foundation | Authentication and Authorization | 7, 8 | Medium |
| 10 | Foundation | Real-Time Infrastructure | 7, 8, 9 | Medium |
| 11 | Dogfood Core | Organizations | 9, 10 | Medium |
| 12 | Dogfood Core | Users and API Key Management | 11 | Medium |
| 13 | Dogfood Core | Projects | 12 | Medium |
| 14 | Dogfood Core | Tasks | 13 | Large |
| 15 | Dogfood Core | Channels and Chat | 13 | Large |
| 16 | Dogfood Core | Comms Bridge | 15 | Large |
| — | **Gate** | **Dogfood Gate: Deploy MC, begin self-hosting** | 11–16 | — |
| 17 | Remaining Features | Sub-Agents | 16 | Medium |
| 18 | Remaining Features | Event Log | 14, 15 | Medium |
| 19 | Remaining Features | Search | 14, 15 | Medium |
| 20 | Remaining Features | Data Export | 11 | Small |
| 21 | Remaining Features | Notifications | 15, 18 | Medium |
| 22 | Release | Deployment and Self-Hosting | All | Medium |

### Parallelization Opportunities

- **POC (Stage 1):** Phases 1–5 can all run in parallel. Phase 6 requires Phases 2 and 3.
- **Foundation (Stage 2):** Phase 7 first; 8 depends on 7; 9 depends on 7, 8; 10 depends on 8, 9. Mostly sequential.
- **Dogfood Core (Stage 3):** Phases 14 (Tasks) and 15 (Channels) can run in parallel after Phase 13 (Projects). Phase 16 (Bridge) requires Phase 15. Mostly sequential due to dependencies but Tasks/Channels overlap.
- **Remaining Features (Stage 4):** Phases 17 (Sub-Agents), 18 (Event Log), 19 (Search), and 20 (Data Export) can all run in parallel — they have no dependencies on each other (only on earlier Dogfood Core phases). Phase 21 (Notifications) depends on Phase 18. **This is the highest-parallelism stage and benefits most from multi-agent coordination through MC.**
- **Release (Stage 5):** Sequential, after all features.
