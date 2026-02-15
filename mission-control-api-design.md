# Mission Control API Design

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

**Task Evidence Requirements:**
When creating or updating a task, the `required_evidence_types` field (array of strings) specifies what must be submitted before the task can be transitioned to `complete`.
- Valid types: `pr_link`, `test_results`, `doc_url`.
- If the array is empty, no evidence is required.

**Transitioning to Complete:**
When transitioning a task to `complete`, the request must include the required evidence if `required_evidence_types` is not empty.

```json
POST /api/v1/orgs/{orgSlug}/tasks/{taskId}/transition
{
  "to_status": "complete",
  "evidence": [
    { "type": "pr_link", "url": "https://github.com/..." },
    { "type": "test_results", "url": "https://ci.example.com/..." }
  ]
}
```

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
