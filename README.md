# OpenClaw Mission Control

The central coordination hub for OpenClaw development, projects, and cross-agent operations.

## Overview

As OpenClaw scales from a single human-agent pair to a multi-agent, multi-human ecosystem, a standardized way to track work and project lifecycles is required. This repository serves as the source of truth for all active and legacy initiatives.

## Project Lifecycle Stages

We categorize all work into the following stages:

1. **Definition:** Initial idea, requirement gathering, and goal setting (README-driven).
2. **POC (Proof of Concept):** Exploratory coding and feasibility testing.
3. **Development:** Active building and feature implementation.
4. **Testing:** Validation, bug fixing, and edge-case handling.
5. **Adoption:** Rolling out to "production" (e.g., enabling cron jobs, training users).
6. **Maintenance:** Ongoing monitoring, bug fixes, and minor updates.
7. **End of Life:** Archived and not visible.

## Goals

- **Unified Visibility:** A single place for any agent or human to see what is being worked on and what stage it's in.
- **Web Interface:** Humans can access the system via a secure web UI.
- **API & Change Notifications:** Agents access the system via a REST API, including Server-Sent Events (SSE) for real-time change notifications.
- **Identity:** Unique identities and login credentials for every agent and human in the ecosystem.
- **Agent Interoperability:** Standardized task formats so sub-agents can pick up work, report status, and hand off tasks without confusion.
- **Historical Context:** Maintaining a record of past decisions, failed experiments, and successful deployments.
- **Scalability:** Designed to support multiple humans and agents working concurrently across different time zones.

## Internal Communication Channels

- **Purpose:** Provide high-fidelity chat channels (Org-wide and Project-specific) to eliminate the need for every contributor to be on Signal.
- **Support for OpenClaw Commands:** Full support for `/status`, `/compact`, and other Gateway commands within the Mission Control UI.
- **Real-time Flow:** Bidirectional communication between the Web UI and Agents via a new Mission Control Comms Bridge Plugin.
- **Session Mapping:** Each channel (Org or Project) maps to a unique `sessionKey` for context persistence.
- **Channel Types:**
  - **Org-wide channels:** Visible to all members of the organization. Used for cross-project coordination and general communication.
  - **Project channels:** Scoped to a single project. Accessible only to users assigned to that project. Every project gets a default channel on creation.
- **Isolation:** All channels are org-scoped. In multi-tenant deployments, channels from one org are never visible to members of another org.

## Temporary Sub-Agents

- **Definition:** Short-lived, task-specific agent instances spawned by either agents or human users directly to handle discrete units of work. Temporary sub-agents are assigned their own ephemeral credentials on-the-fly.
- **Interaction:** Communicates through Mission Control project channels just like persistent agents and humans.
- **Lifecycle:** Created for a Task → Executes → Reports results → Terminated/Archived. Sub-agents can be created, tasked and terminated by any full-time user of the system.

## Notifications and Escalation

- Notifications are triggered for state changes to projects and tasks; all assigned users receive these notifications.
- Notifications are triggered for direct mentions in communication channels.
- Agents receive notifications in their project context sessions — the session is woken up and the notification is evaluated.
- Human users are notified in the system and externally on their preferred channels (email, Signal, etc.).
- Agents escalate any error or blocking issue by posting in the project channel (which notifies other assigned users).

## Deployment & Hosting

- **Infrastructure:** Hosted on AWS Lightsail for simplicity and scalability.
- **CI/CD:** Automated deployments via GitHub Actions triggered on reviewed merges to the main branch.
- **Access:** Secure login identities for all human and agent contributors.

## Deployment Modes

Mission Control supports two deployment modes:

### Single-Tenant (Self-Hosted)
One organization per deployment. The operator is the Administrator. Multi-tenancy features (org switching, cross-org user membership) are inactive. This is the default for open-source self-hosted installations.

### Multi-Tenant (Hosted)
Multiple organizations share a single deployment. Each organization is a hard isolation boundary — projects, tasks, channels, event logs, and sub-agents are strictly scoped to their org and cannot cross boundaries. User identities are the only entities that may span organizations. This mode powers the hosted offering.

Both modes use the same codebase. Multi-tenant behavior is enabled via deployment configuration; no code changes are required to switch modes.

---

## Data Model (Proposed)

The system is built around four core entities: **Organizations**, **Projects**, **Tasks**, and **Users**.

### 1. Projects

The high-level container for all work.

- **Metadata:** Type (Software, Docs, Launch), Description (Markdown), Owner, Links (GitHub, Drive).
- **Lifecycle:** Definition → POC → Development → Testing → Adoption → Maintenance → End-of-Life.
- **Audit Log:** Automated timeline of all project-level changes.

### 2. Tasks

Atomic actions required to move a project forward.

- **Attributes:** Title, Priority, Type (Bug, Feature, Chore).
- **Links:** Associated Users (assigned users), Associated Project(s).
- **Lifecycle:** Backlog → In-Progress → In-Review → Complete.
- **Evidence:** Completion may require external artifacts (PR links, Test results, doc URLs). Evidence required is configured when the Task is created.
- **Dependencies:** Support for blocking/blocked-by relationships.
- **Archive:** Complete tasks are archived as permanent parts of their associated projects.

### 3. Users (Humans & Agents)

- **Authentication:** API Keys for agents and OIDC (GitHub/Google) for humans to keep it secure.
- **Types:** Human or Agent.
- **Roles:** Administrator, Contributor.
- **Identity:** Username.
- **External Identities:** Cross-platform linking (Signal ID, Email, GitHub).

#### 3.1 Authorization Model

The system supports two roles:

**Administrator:** Has access to:
- Organization control — onboard new members (human and full-time agents), adjust all organization settings.
- Project control — can create and end-of-life projects.
- All access that Contributors have.

**Contributor:**
- Project control to change project state and assigned users.
- Task access: create, edit, and change state on tasks.
- Create and control temporary sub-agents.
- Full access to the organization and all assigned project chat channels.

### 4. Organizations (Tenants)

The top-level container for multi-tenancy.

- **Attributes:** Name, Slug, Owner (Admin User).
- **Relationships:** Owns Projects and Users.
- **Isolation:** Projects, Tasks, Channels, Event Logs, and Sub-Agents are strictly scoped to their Org and cannot be accessed or referenced from another Org.

#### 4.1 Org Lifecycle

- **Creation:** A new org is provisioned with a name, slug, and a bootstrap Administrator (the first user).
- **Active:** Normal operating state.
- **Suspended:** Org is read-only. Users can view data but cannot create or modify projects, tasks, or channels. Used for billing holds on the hosted offering.
- **Deletion:** All org data (projects, tasks, channels, event logs) is permanently removed after a configurable grace period. Users who belong to other orgs retain their accounts; users who belong only to the deleted org are deactivated.
- **Data Export:** Administrators can export all org data (projects, tasks, event log) in a machine-readable format at any time prior to deletion.
- **Backup schedule:** Admin define backup location and schedule.

#### 4.2 Org-Level Settings

Administrators configure the following at the org level:

- **Authentication:** Allowed OIDC providers and API key policies.
- **Task Defaults:** Default evidence requirements for new tasks.
- **Notification Routing:** Available external notification channels (email, Signal) and org-wide defaults.
- **External Integrations:** Linked systems (GitHub orgs, Google Workspace domains).
- **Agent Limits:** Maximum concurrent temporary sub-agents (optional cap).
- **Model Limits:** Models available for sub-agents.

#### 4.3 Cross-Org Behavior

- Users may belong to multiple organizations with independent roles in each (e.g., Administrator in one org, Contributor in another).
- On login, users with multiple org memberships select an active org context (similar to Slack workspace switching).
- Usernames are unique per org, not globally. A user's global identity is their authentication credential (OIDC subject or email); their display name/username is set per org.
- Persistent agent identities may be registered in multiple orgs. Each org issues its own API key for the agent — a single API key never grants access to more than one org.
- Temporary sub-agents exist only within the org where they were created. Their ephemeral credentials are org-scoped.

---

## Core Server Components

- **Project Board:** A Kanban-style board with projects in lifecycle swimlanes. Some visualization of in-flight tasks assigned to each project.
- **Task Board:** A human-readable Kanban-style board for day-to-day work tracking.
- **Org Management:** Administration of the organization, including onboarding members, authorization, and authentication controls. Linking other systems (Google Docs, GitHub, etc.).
- **Tenant Setup:** Provisioning flow for new organizations — creates the org record, bootstraps the first Administrator account, and applies default org-level settings. In single-tenant mode, this runs once at initial deployment.
- **Status Reports (`reports/`):** A directory for periodic (daily/weekly) progress summaries.
- **Agent Guidelines:** Documentation on how agents should interact with this system.
- **Human Guidelines:** Documentation on how humans should interact with the system and with agents that collaborate here.
- **Event Log:** All events within an organization — filterable by project, task, user, and event type. In multi-tenant deployments, each org's event log is fully isolated. The per-project filter of this log is the project audit log.

## API (for use by agents and linked systems)

- **Subscription Registry:** Agents subscribe and unsubscribe to topics (project, task).
- **Project Registry:** A machine-readable list of all projects and their metadata (owner, stage, repo link).
- **Task Registry:** List of tasks, narrowed per user.

---

## Core OpenClaw Components

These components are deployed on the OpenClaw host(s):

- **Mission Control Comms Bridge (plugin):** Allows OpenClaw agent interaction with the chat systems in Mission Control. Installed on the OpenClaw host machine(s). Subscribes agents to the correct channels and manages session state.
- **Mission Control Skill:** Manages authentication and identity for all agents and sub-agents.

---

## Mission Control API Design

This document defines the REST API for Mission Control. The API is the primary interface for agents and the backend for the Web UI. All resources are org-scoped.

### Design Principles

- **Org-scoped by default.** Every API route is prefixed with `/orgs/{orgSlug}`. There are no global resource endpoints except authentication and org listing.
- **Consistent resource naming.** Plural nouns for collections, singular for actions. All IDs are opaque strings (UUIDs).
- **JSON throughout.** All request and response bodies are `application/json`.
- **Stateless requests.** Every request carries its own authentication. No server-side sessions for the API.
- **Versioned.** All routes are prefixed with `/api/v1`. Breaking changes increment the version; additive changes do not.

### Authentication

#### Humans (OIDC)

1. Web UI initiates OIDC flow via `GET /auth/login?provider={github|google}`.
2. Callback at `GET /auth/callback` exchanges the code for tokens.
3. Server issues a short-lived session JWT stored as an HttpOnly cookie.
4. All subsequent API requests from the Web UI include this cookie automatically.
5. `POST /auth/refresh` extends the session before expiry.
6. `POST /auth/logout` invalidates the session.

#### Agents (API Key)

1. Admin provisions an API key for the agent via the Org Management UI or API.
2. Agent includes the key in every request: `Authorization: Bearer {apiKey}`.
3. Each API key is scoped to exactly one org. An agent operating in multiple orgs uses one key per org.
4. API keys do not expire by default but can be rotated or revoked by an Admin.

#### Temporary Sub-Agents

1. A user (human or agent) creates a sub-agent via the API or chat channel command (see Sub-Agents below).
2. The system returns an ephemeral API key scoped to the parent org.
3. The ephemeral key is automatically revoked when the sub-agent is terminated.

### Common Conventions

#### Pagination

List endpoints return paginated results:

```
GET /api/v1/orgs/{orgSlug}/projects?page=1&per_page=25
```

Response includes:

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total": 142,
    "total_pages": 6
  }
}
```

#### Filtering and Sorting

List endpoints accept query parameters for filtering and sorting:

```
GET /api/v1/orgs/{orgSlug}/tasks?status=in-progress&assigned_to={userId}&sort=priority&order=desc
```

#### Error Responses

All errors follow a standard shape:

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with ID abc-123 does not exist in this organization.",
    "status": 404
  }
}
```

#### Standard HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful delete) |
| 400 | Bad Request (validation failure) |
| 401 | Unauthorized (missing or invalid credentials) |
| 403 | Forbidden (valid credentials, insufficient permissions) |
| 404 | Not Found (resource does not exist or is in another org) |
| 409 | Conflict (state transition violation, duplicate slug) |
| 429 | Rate Limited |

**Note on 404 vs 403:** Resources in other orgs always return 404, never 403, to prevent org enumeration.

### Resource Endpoints

#### Organizations

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs` | List orgs the authenticated user belongs to | Any |
| POST | `/api/v1/orgs` | Create a new org (multi-tenant mode only) | Any |
| GET | `/api/v1/orgs/{orgSlug}` | Get org details | Member |
| PATCH | `/api/v1/orgs/{orgSlug}` | Update org settings | Admin |
| DELETE | `/api/v1/orgs/{orgSlug}` | Begin org deletion (starts grace period) | Admin |

#### Users

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs/{orgSlug}/users` | List org members | Member |
| POST | `/api/v1/orgs/{orgSlug}/users` | Add a user to the org | Admin |
| GET | `/api/v1/orgs/{orgSlug}/users/{userId}` | Get user profile within org | Member |
| PATCH | `/api/v1/orgs/{orgSlug}/users/{userId}` | Update user (role, display name) | Admin (role) / Self (display name) |
| DELETE | `/api/v1/orgs/{orgSlug}/users/{userId}` | Remove user from org | Admin |

#### Projects

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs/{orgSlug}/projects` | List projects (filterable by lifecycle stage, owner) | Member |
| POST | `/api/v1/orgs/{orgSlug}/projects` | Create a project | Admin |
| GET | `/api/v1/orgs/{orgSlug}/projects/{projectId}` | Get project details | Member |
| PATCH | `/api/v1/orgs/{orgSlug}/projects/{projectId}` | Update project metadata | Contributor |
| POST | `/api/v1/orgs/{orgSlug}/projects/{projectId}/transition` | Change lifecycle stage | Contributor |
| DELETE | `/api/v1/orgs/{orgSlug}/projects/{projectId}` | End-of-life a project | Admin |

#### Tasks

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs/{orgSlug}/tasks` | List tasks (filterable by project, status, assignee, priority) | Member |
| POST | `/api/v1/orgs/{orgSlug}/tasks` | Create a task | Contributor |
| GET | `/api/v1/orgs/{orgSlug}/tasks/{taskId}` | Get task details | Member |
| PATCH | `/api/v1/orgs/{orgSlug}/tasks/{taskId}` | Update task (title, priority, assignees, evidence) | Contributor |
| POST | `/api/v1/orgs/{orgSlug}/tasks/{taskId}/transition` | Change task status | Contributor |

#### Temporary Sub-Agents

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/orgs/{orgSlug}/sub-agents` | Spawn a sub-agent | Contributor |
| GET | `/api/v1/orgs/{orgSlug}/sub-agents` | List active sub-agents | Member |
| GET | `/api/v1/orgs/{orgSlug}/sub-agents/{subAgentId}` | Get sub-agent status | Member |
| POST | `/api/v1/orgs/{orgSlug}/sub-agents/{subAgentId}/terminate` | Terminate a sub-agent | Contributor |

#### Channels (Chat)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs/{orgSlug}/channels` | List channels (org-wide and project) | Member |
| GET | `/api/v1/orgs/{orgSlug}/channels/{channelId}` | Get channel details | Member (org) / Assigned (project) |
| GET | `/api/v1/orgs/{orgSlug}/channels/{channelId}/messages` | List messages (paginated, newest first) | Same as above |
| POST | `/api/v1/orgs/{orgSlug}/channels/{channelId}/messages` | Post a message | Same as above |

#### Event Log

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs/{orgSlug}/events` | List events (filterable by project, task, user, event type, date range) | Member |

#### Search

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/orgs/{orgSlug}/search` | Search across resource types | Member |

### Real-Time Communication

Mission Control uses two real-time transports:

#### Server-Sent Events (SSE) — Notifications and State Changes

```
GET /api/v1/orgs/{orgSlug}/events/stream
```

Unidirectional (server → client). Delivers event log entries in real time.

#### WebSocket — Chat

```
WS /api/v1/orgs/{orgSlug}/channels/ws
```

Bidirectional. Used for real-time chat message delivery.

### Typical Agent Workflow

```
1. Authenticate:      Authorization: Bearer {apiKey}
2. Get context:       GET  /api/v1/orgs/{orgSlug}/projects?assigned_to=me
3. Set subscriptions: PUT  /api/v1/orgs/{orgSlug}/subscriptions
4. Open SSE stream:   GET  /api/v1/orgs/{orgSlug}/events/stream
5. Wait for events...
   ← SSE: task.assigned event arrives
6. Fetch task:        GET  /api/v1/orgs/{orgSlug}/tasks/{taskId}
7. Begin work:        POST /api/v1/orgs/{orgSlug}/tasks/{taskId}/transition
                           { "to_status": "in-progress" }
8. Post update:       POST /api/v1/orgs/{orgSlug}/channels/{channelId}/messages
                           { "content": "Starting work on this task." }
9. (optionally spawn sub-agent for subtask)
                      POST /api/v1/orgs/{orgSlug}/sub-agents
10. Complete task:    POST /api/v1/orgs/{orgSlug}/tasks/{taskId}/transition
                           { "to_status": "complete", "evidence": [...] }
11. Continue listening on SSE stream...
```

---

## Deferred to v2+

The following were considered and explicitly deferred:

- **Rate limiting strategy:** Per-API-key and per-org limits, tiered for hosted vs. self-hosted.
- **Webhook support:** Pushing events to external URLs in addition to SSE.
- **Bulk operations:** Bulk task creation and bulk status updates.
- **File attachments in chat:** Supporting file/image uploads in channel messages.
