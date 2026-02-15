# Mission Control Frontend Architecture

This document defines the frontend architecture for Mission Control's Web UI. It covers application structure, routing, state management, real-time data flow, component design, and offline/reconnection behavior. Framework choices (Vue 3, TypeScript, Pinia, Tailwind) are established in the tech stack document; this document focuses on how they're applied.

---

## Application Shell

The UI is organized as a single-page application with a persistent shell layout that wraps all org-scoped views.

```
┌──────────────────────────────────────────────────────┐
│  Top Bar                                             │
│  [Org Switcher ▾]   [Search]          [Notifications]│
├────────────┬─────────────────────────────────────────┤
│            │                                         │
│  Sidebar   │  Main Content Area                      │
│            │                                         │
│  Projects  │  (routed view: board, task list,        │
│  Tasks     │   channel, settings, etc.)              │
│  Channels  │                                         │
│  Events    │                                         │
│  Settings  │                                         │
│            │                                         │
│            │                                         │
│            │                                         │
├────────────┴─────────────────────────────────────────┤
│  Status Bar                                          │
│  [SSE: Connected]  [WS: Connected]  [v0.1.0]        │
└──────────────────────────────────────────────────────┘
```

**Top Bar:** Org switcher (for multi-org users), global search input, and notification tray. Always visible.

**Sidebar:** Navigation scoped to the active org. Shows project list (grouped by lifecycle stage), channel list (org-wide and project), and links to task board, event log, and org settings. Collapsible on narrow viewports.

**Main Content Area:** The routed view. Changes based on URL.

**Status Bar:** Connection status indicators for SSE and WebSocket. Visible in development and optionally in production. Shows reconnection state when connections are degraded.

---

## Routing

Routes are org-scoped, matching the API's URL structure. The org slug is a route parameter on all views except login and org selection.

```typescript
// router/index.ts

const routes = [
  // Auth (no org context)
  { path: "/login",               component: LoginView },
  { path: "/auth/callback",       component: AuthCallbackView },
  { path: "/orgs",                component: OrgSelectView },

  // Org-scoped views
  {
    path: "/orgs/:orgSlug",
    component: OrgLayout,          // shell layout with sidebar + top bar
    children: [
      { path: "",                  redirect: "projects" },
      { path: "projects",         component: ProjectBoardView },
      { path: "projects/:id",     component: ProjectDetailView },
      { path: "tasks",            component: TaskBoardView },
      { path: "tasks/:id",        component: TaskDetailView },
      { path: "channels/:id",     component: ChannelView },
      { path: "events",           component: EventLogView },
      { path: "search",           component: SearchView },
      { path: "settings",         component: OrgSettingsView },
      { path: "settings/users",   component: UserManagementView },
      { path: "sub-agents",       component: SubAgentListView },
    ],
  },
]
```

### Route Guards

**Auth guard:** All routes except `/login` and `/auth/callback` require a valid session. If the session cookie is missing or expired, the user is redirected to `/login`. The guard checks the auth store, not the cookie directly (the store is hydrated from a `GET /auth/me` call on app init).

**Org guard:** All org-scoped routes validate that the user is a member of the org in the URL. If not, redirect to `/orgs` (org selection). This prevents URL manipulation from exposing another org's views (the API would return 404 anyway, but the guard provides a clean UX).

**Role guard:** Admin-only routes (`/settings`, `/settings/users`) check the user's role in the active org. Contributors are shown a 403 view with an explanation, not a redirect.

---

## State Management

### Store Architecture

Pinia stores are organized by domain. Each store owns its data, loading state, and error state. Stores do not call each other directly — they communicate through the real-time event system (SSE events update multiple stores simultaneously).

```
stores/
├── auth.ts            # Session, active org, user profile, org switching
├── projects.ts        # Project list, lifecycle state, board layout
├── tasks.ts           # Task list, status, assignments, dependencies
├── channels.ts        # Channel list, active channel, message history
├── events.ts          # Event log entries, filters
├── search.ts          # Search query, results, filters
├── notifications.ts   # Notification queue, read/unread state
├── subAgents.ts       # Active sub-agents list
├── realtime.ts        # SSE/WS connection state, reconnection status
└── ui.ts              # Sidebar collapsed, active view, preferences
```

### Store Pattern

Each domain store follows a consistent pattern:

```typescript
// stores/projects.ts

export const useProjectStore = defineStore("projects", () => {
  // State
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Derived state
  const byStage = computed(() =>
    groupBy(projects.value, (p) => p.stage)
  )

  // API actions
  async function fetchProjects() {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.projects.list()
      projects.value = data
    } catch (e) {
      error.value = extractErrorMessage(e)
    } finally {
      loading.value = false
    }
  }

  async function transitionProject(id: string, toStage: string, comment?: string) {
    await api.projects.transition(id, { to_stage: toStage, comment })
    // Optimistic update removed intentionally — SSE event will update state.
    // This ensures consistency: the board reflects what the server confirmed.
  }

  // SSE event handler (called by the realtime composable)
  function handleEvent(event: MCEvent) {
    switch (event.type) {
      case "project.created":
        projects.value.push(event.payload.project)
        break
      case "project.updated":
        const idx = projects.value.findIndex(p => p.id === event.payload.project.id)
        if (idx !== -1) projects.value[idx] = event.payload.project
        break
      case "project.transitioned":
        const pidx = projects.value.findIndex(p => p.id === event.payload.project_id)
        if (pidx !== -1) projects.value[pidx].stage = event.payload.to_stage
        break
    }
  }

  return { projects, loading, error, byStage, fetchProjects, transitionProject, handleEvent }
})
```

### No Optimistic Updates

State-changing actions (transitions, creates, updates) do **not** optimistically update the store. Instead, the action fires the API call, and the store waits for the SSE event to confirm the change. This is a deliberate trade-off:

- **Pro:** The UI always reflects the server-confirmed state. No rollback logic. No inconsistency between what the user sees and what actually happened.
- **Con:** There is a brief delay (~100–500ms) between clicking "Move to Development" and seeing the card move on the Kanban board. This is acceptable for this application — it's a project management tool, not a real-time game.

The one exception is **chat messages**: the channels store uses optimistic insert (with a `pending` flag) and replaces with the server-confirmed message when the WebSocket echo arrives. This is necessary because chat has higher latency sensitivity than board interactions.

---

## Real-Time Data Flow

### SSE: Event Stream

The SSE connection is managed by a composable that handles connection lifecycle, reconnection, and event dispatch to stores.

```typescript
// composables/useSSE.ts

export function useSSE() {
  const realtimeStore = useRealtimeStore()
  const projectStore = useProjectStore()
  const taskStore = useTaskStore()
  const notificationStore = useNotificationStore()
  const subAgentStore = useSubAgentStore()

  let eventSource: EventSource | null = null
  let reconnectAttempts = 0

  function connect(orgSlug: string) {
    const url = `/api/v1/orgs/${orgSlug}/events/stream`
    eventSource = new EventSource(url, { withCredentials: true })

    eventSource.onopen = () => {
      realtimeStore.setSseStatus("connected")
      reconnectAttempts = 0
    }

    eventSource.onmessage = (event) => {
      const parsed: MCEvent = JSON.parse(event.data)
      dispatch(parsed)
    }

    eventSource.onerror = () => {
      realtimeStore.setSseStatus("reconnecting")
      eventSource?.close()
      scheduleReconnect(orgSlug)
    }
  }

  function dispatch(event: MCEvent) {
    // Route event to the appropriate store(s)
    const prefix = event.type.split(".")[0]

    switch (prefix) {
      case "project":
        projectStore.handleEvent(event)
        break
      case "task":
        taskStore.handleEvent(event)
        break
      case "sub_agent":
        subAgentStore.handleEvent(event)
        break
    }

    // Notifications are cross-cutting — all events may generate one
    notificationStore.evaluate(event)
  }

  function scheduleReconnect(orgSlug: string) {
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 60000)
    reconnectAttempts++
    setTimeout(() => connect(orgSlug), delay)
  }

  function disconnect() {
    eventSource?.close()
    eventSource = null
    realtimeStore.setSseStatus("disconnected")
  }

  return { connect, disconnect }
}
```

**Key behaviors:**

- Reconnection uses exponential backoff (1s, 2s, 4s, ... capped at 60s).
- `withCredentials: true` ensures the session cookie is sent with the SSE request.
- Event dispatch is synchronous — stores update reactively, and Vue's reactivity system batches DOM updates.
- The browser's native `EventSource` handles `Last-Event-ID` automatically on reconnection.

### WebSocket: Chat

The WebSocket connection is managed by a separate composable. It handles channel multiplexing (all channels over one connection), reconnection, and message dispatching.

```typescript
// composables/useWebSocket.ts

export function useWebSocket() {
  const realtimeStore = useRealtimeStore()
  const channelStore = useChannelStore()

  let ws: WebSocket | null = null
  let reconnectAttempts = 0
  let heartbeatTimer: number | null = null

  function connect(orgSlug: string) {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:"
    const url = `${protocol}//${location.host}/api/v1/orgs/${orgSlug}/channels/ws`
    ws = new WebSocket(url)

    ws.onopen = () => {
      realtimeStore.setWsStatus("connected")
      reconnectAttempts = 0
      startHeartbeat()
    }

    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data)
      handleFrame(frame)
    }

    ws.onclose = (event) => {
      stopHeartbeat()
      if (event.code === 4001) {
        // Auth revoked — do not reconnect, redirect to login
        realtimeStore.setWsStatus("auth_revoked")
        return
      }
      realtimeStore.setWsStatus("reconnecting")
      scheduleReconnect(orgSlug)
    }

    ws.onerror = () => {
      // onerror is always followed by onclose; reconnection handled there
    }
  }

  function handleFrame(frame: WSFrame) {
    switch (frame.type) {
      case "message":
        channelStore.receiveMessage(frame)
        break
      case "typing":
        channelStore.setTypingIndicator(frame.channel_id, frame.sender_id, true)
        break
      case "typing_stopped":
        channelStore.setTypingIndicator(frame.channel_id, frame.sender_id, false)
        break
      case "pong":
        // heartbeat acknowledged, connection is alive
        break
    }
  }

  function send(frame: WSFrame) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(frame))
    } else {
      // Queue for delivery after reconnection
      channelStore.queueOutbound(frame)
    }
  }

  function startHeartbeat() {
    heartbeatTimer = window.setInterval(() => {
      send({ type: "ping" })
    }, 30000)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) clearInterval(heartbeatTimer)
  }

  function scheduleReconnect(orgSlug: string) {
    const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000)
    reconnectAttempts++
    setTimeout(() => connect(orgSlug), delay)
  }

  function disconnect() {
    ws?.close()
    ws = null
    stopHeartbeat()
    realtimeStore.setWsStatus("disconnected")
  }

  return { connect, disconnect, send }
}
```

**Key behaviors:**

- Single WebSocket connection per org, multiplexing all channels.
- Client-side ping/pong heartbeat every 30 seconds detects dead connections faster than TCP keepalive.
- Close code `4001` (auth revoked) triggers login redirect, not reconnection.
- Messages sent while disconnected are queued in the channel store and flushed on reconnection.

---

## Offline and Reconnection Behavior

### Connection States

The realtime store tracks connection health:

```typescript
// stores/realtime.ts

type ConnectionStatus = "connected" | "reconnecting" | "disconnected" | "auth_revoked"

export const useRealtimeStore = defineStore("realtime", () => {
  const sseStatus = ref<ConnectionStatus>("disconnected")
  const wsStatus = ref<ConnectionStatus>("disconnected")
  const sseReconnectAttempts = ref(0)
  const wsReconnectAttempts = ref(0)

  const isFullyConnected = computed(
    () => sseStatus.value === "connected" && wsStatus.value === "connected"
  )

  const isDegraded = computed(
    () => sseStatus.value === "reconnecting" || wsStatus.value === "reconnecting"
  )

  // ...setters, reset
})
```

### UI Indicators

| State | Visual Indicator |
|-------|-----------------|
| Both connected | Status bar shows green dot (or hidden entirely in production) |
| SSE reconnecting | Yellow banner at top of main content: "Live updates paused. Reconnecting..." |
| WS reconnecting | Yellow badge on chat icon in sidebar. Messages typed during disconnection are queued and show a pending indicator. |
| Both disconnected | Red banner: "Connection lost. Your changes may not be saved. Retrying..." |
| Auth revoked | Modal overlay: "Your session has expired. Please log in again." with login redirect button. |

### Data Freshness During Disconnection

When SSE reconnects, there may be events that were missed during the gap. Two strategies handle this:

**EventSource `Last-Event-ID`:** The browser's native EventSource sends the last received event ID (`sequence_id` from the database) on reconnection. The server replays missed events from the database or its hot buffer. This handles disconnections and server restarts seamlessly.

**Full refresh on `events.reset`:** If the server cannot replay the requested ID (e.g., the ID is too old and the partition has been archived), it sends an `events.reset` event. Upon receiving this, the stores perform a full data refresh:

```typescript
// composables/useSSE.ts (inside connect, handle reset event)

function dispatch(event: MCEvent) {
  if (event.type === "events.reset") {
    // Replay impossible — full refresh
    projectStore.fetchProjects()
    taskStore.fetchTasks()
    subAgentStore.fetchSubAgents()
    return
  }
  // ... existing dispatch logic ...
}
```

This ensures the UI never shows stale Kanban board state after a long disconnection.

### Chat Message Handling During Disconnection

| Scenario | Behavior |
|----------|----------|
| User types a message while WS is down | Message is added to the channel store's outbound queue with `status: "queued"`. Displayed in the chat with a clock icon. |
| WS reconnects | Queued messages are flushed via REST (`POST /channels/{id}/messages`) as a fallback, since the WebSocket state may not support immediate send. |
| Queued message fails to send | Message status changes to `"failed"`. Displayed with a retry button. User can click to resend or dismiss. |
| Incoming messages missed during WS downtime | On reconnect, the channel store fetches the latest messages via REST (`GET /channels/{id}/messages?after={lastMessageId}`) and merges them into the local message list. |

---

## View Components

### Project Board (`ProjectBoardView.vue`)

Kanban board with lifecycle stage columns. Projects are cards within columns.

```
┌─────────────┬─────────────┬─────────────┬─────────────┬───────┐
│ Definition  │ POC         │ Development │ Testing     │ ...   │
├─────────────┼─────────────┼─────────────┼─────────────┼───────┤
│ ┌─────────┐ │ ┌─────────┐ │ ┌─────────┐ │             │       │
│ │Project A│ │ │Project C│ │ │Project B│ │             │       │
│ │ 3 tasks │ │ │ 1 task  │ │ │ 7 tasks │ │             │       │
│ │ Owner:J │ │ │ Owner:A │ │ │ Owner:J │ │             │       │
│ └─────────┘ │ └─────────┘ │ ├─────────┤ │             │       │
│             │             │ │Project D│ │             │       │
│             │             │ │ 2 tasks │ │             │       │
│             │             │ └─────────┘ │             │       │
└─────────────┴─────────────┴─────────────┴─────────────┴───────┘
```

**Project card contents:** Name, owner avatar/name, task count (with status breakdown shown as a small progress bar), project type badge.

**Interactions:**
- Drag a project card between columns to trigger a lifecycle transition. Drop is validated client-side (only adjacent stages or backward transitions). Invalid drops snap back with a tooltip explaining why.
- Click a project card to navigate to `ProjectDetailView`.
- "New Project" button in the Definition column (Admin only).

**Real-time updates:** SSE `project.transitioned` events move cards between columns with a brief animation. SSE `project.updated` events update card metadata in place. New projects appear in the Definition column.

### Task Board (`TaskBoardView.vue`)

Kanban board with status columns. Tasks are cards within columns.

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ Backlog      │ In Progress  │ In Review    │ Complete     │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐ │
│ │ Task 1   │ │ │ Task 3   │ │ │ Task 5   │ │ │ Task 7   │ │
│ │ High 🔴  │ │ │ Med  🟡  │ │ │ High 🔴  │ │ │ Low  🟢  │ │
│ │ @agent01 │ │ │ @jane    │ │ │ @jane    │ │ │ @agent01 │ │
│ │ Proj B   │ │ │ Proj B   │ │ │ Proj A   │ │ │ Proj A   │ │
│ └──────────┘ │ └──────────┘ │ └──────────┘ │ └──────────┘ │
│ ┌──────────┐ │              │              │              │
│ │ Task 2   │ │              │              │              │
│ │ Low  🟢  │ │              │              │              │
│ │ @agent02 │ │              │              │              │
│ │ Proj C   │ │              │              │              │
│ └──────────┘ │              │              │              │
└──────────────┴──────────────┴──────────────┴──────────────┘

Filters: [Project ▾] [Assignee ▾] [Priority ▾] [My Tasks]
```

**Task card contents:** Title, priority indicator, assignee avatar(s), project badge(s), dependency warning icon (if blocked).

**Interactions:**
- Drag between status columns to trigger a transition. Dragging to Complete opens an evidence submission modal if evidence is required.
- Click to open `TaskDetailView` (slide-over panel or dedicated page).
- Filter bar above the board scopes visible tasks by project, assignee, or priority. "My Tasks" filter shows only tasks assigned to the current user.
- "New Task" button opens a creation form.

**Real-time updates:** SSE `task.transitioned` events move cards between columns. `task.updated` events refresh card content. New tasks appear in Backlog.

### Channel View (`ChannelView.vue`)

Chat interface for a single channel (org-wide or project).

```
┌──────────────────────────────────────────────────────┐
│ # Project B Channel                     [Members: 4] │
├──────────────────────────────────────────────────────┤
│                                                      │
│  jane (10:15 AM)                                     │
│  Can you review the PR for the auth module?          │
│                                                      │
│  builder-agent-01 (10:16 AM)               [agent]   │
│  PR reviewed. Found 2 issues, posted comments on     │
│  GitHub.                                             │
│                                                      │
│  jane (10:18 AM)                                     │
│  /status                                             │
│                                                      │
│  builder-agent-01 (10:18 AM)               [agent]   │
│  Project B: Development | 5/7 tasks complete         │
│  Active: Task 3 (in-progress), Task 6 (in-review)   │
│                                                      │
├──────────────────────────────────────────────────────┤
│  builder-agent-01 is typing...                       │
├──────────────────────────────────────────────────────┤
│  [Message input]                          [Send]     │
│  Type a message... @mention with @, commands with /  │
└──────────────────────────────────────────────────────┘
```

**Message display:**
- Messages from agents show an `[agent]` badge.
- Timestamps are relative ("2 min ago") for recent messages, absolute ("Feb 13, 10:15 AM") for older ones.
- Mentions (`@jane`) are highlighted.
- Command outputs (from `/status`, `/compact`) are rendered in a distinct style (monospace background block).

**Interactions:**
- Type `@` to trigger a mention autocomplete dropdown (searches org members).
- Type `/` to trigger a command autocomplete dropdown (lists available commands).
- Messages are sent via WebSocket. If WebSocket is down, the input field shows a "reconnecting" state and queues the message.
- Scroll to top triggers paginated history loading via REST (`GET /channels/{id}/messages?page=2`).

**Real-time updates:** WebSocket delivers new messages. Typing indicators show when another user is composing a message (debounced, clears after 3 seconds of inactivity).

### Event Log (`EventLogView.vue`)

Filterable log of all org events. Uses **AG Grid** for high-density data management.

**Real-time updates:** SSE events append new entries at the top of the grid.

**Filters:** Column-level filtering provided by AG Grid (type, actor, project, etc.) replaces manual filter controls.

### Search (`SearchView.vue`)

Unified search across projects, tasks, and messages.

```
┌──────────────────────────────────────────────────────┐
│  Search: [deploy staging          ]                  │
│  Filters: [All Types ▾] [Project ▾] [Date Range ▾]  │
├──────────────────────────────────────────────────────┤
│                                                      │
│  Tasks (12 results)                                  │
│  ┌──────────────────────────────────────────────┐    │
│  │ Deploy staging environment          in-progress│   │
│  │ ...configure the **deploy** pipeline for       │   │
│  │ **staging**...                                 │   │
│  │ Project: Infrastructure                        │   │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  Messages (23 results)                               │
│  ┌──────────────────────────────────────────────┐    │
│  │ builder-agent-01 in #project-infra  10:20 AM │    │
│  │ Build passed. **Deploying** to **staging** now.│   │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  Projects (2 results)                                │
│  ┌──────────────────────────────────────────────┐    │
│  │ Infrastructure                    development │    │
│  │ ...manages **staging** and production          │   │
│  │ **deploy**ment...                              │   │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  Page 1 of 3  [Next →]                              │
└──────────────────────────────────────────────────────┘
```

**Behavior:**
- Search is debounced (300ms after the user stops typing).
- Results are grouped by resource type with counts.
- Snippets use `<mark>` highlighting from the API response (rendered safely via `v-html` on sanitized server output — the server controls the markup, not user input).
- Clicking a result navigates to the resource's detail view.
- Search query and filters are reflected in the URL for shareability.

### Org Settings (`OrgSettingsView.vue`)

Admin-only view for org configuration.

**Sections (tab navigation):**
- **General:** Org name, slug (read-only after creation).
- **Authentication:** OIDC provider toggles, API key policies.
- **Defaults:** Task evidence requirements, notification routing.
- **Integrations:** GitHub org link, Google Workspace domain.
- **Agent Limits:** Max concurrent sub-agents, allowed models.
- **Danger Zone:** Org deletion (with confirmation modal and grace period explanation).

### User Management (`UserManagementView.vue`)

Admin-only view for managing org members. Uses **AG Grid** for high-density member administration.

**Table layout:** Columnar layout managed by AG Grid (Name, type, role, last active, actions).

### Task Table View (Alternate View)

In addition to the Kanban board, users can toggle to a **Task Table View** (powered by AG Grid) for bulk operations, advanced sorting, and multi-column filtering.

**Interactions:**
- "Invite User" button opens a form (email for humans, identifier for agents).
- Agent rows show a "Rotate API Key" button that triggers the rotation flow (confirmation modal, new key shown once, copy-to-clipboard).
- Role changes take effect immediately (SSE event updates the table for other admins viewing the same page).

---

## Notification System

### In-App Notifications

The notification store evaluates every SSE event and generates a notification if the event is relevant to the current user:

| Event | Generates Notification When |
|-------|----------------------------|
| `task.assigned` | Current user is the assignee |
| `task.transitioned` | Current user is assigned to the task |
| `message.created` | Current user is mentioned, or message is in a channel the user has open |
| `sub_agent.terminated` | Current user created the sub-agent |
| `project.transitioned` | Current user is the project owner |

**Notification tray:** Bell icon in the top bar with unread count badge. Opens a dropdown showing recent notifications. Each notification links to the relevant resource. Notifications are marked read on click.

**Toast notifications:** High-priority events (direct mentions, task assignments) also show a brief toast notification that auto-dismisses after 5 seconds.

**No persistence:** Notifications are in-memory only (within the Pinia store). They are not stored server-side. Closing the browser clears them. This is a v1 simplification — server-side notification persistence with read/unread state can be added later without changing the frontend architecture.

---

## Responsive Behavior

The UI targets three breakpoints:

| Breakpoint | Layout | Sidebar | Behavior |
|------------|--------|---------|----------|
| Desktop (≥1280px) | Full shell | Always visible | Default experience |
| Tablet (768–1279px) | Full shell | Collapsed by default, toggleable | Kanban boards scroll horizontally |
| Mobile (<768px) | Stacked | Hidden, hamburger menu | Kanban boards show one column at a time with swipe navigation. Chat is full-screen. |

Kanban drag-and-drop is disabled on touch devices — use a "Move to..." dropdown instead.

---

## API Client

The API client is generated from the server's OpenAPI spec, providing typed request and response interfaces.

### Type Generation Pipeline

```bash
# 1. Export OpenAPI spec from FastAPI
python scripts/export-openapi.py > frontend/src/api/openapi.json

# 2. Generate TypeScript types
cd frontend && npx openapi-typescript src/api/openapi.json -o src/api/types.ts
```

This runs in CI after any change to `packages/server/app/schemas/` or `packages/shared/`, ensuring the frontend types stay synchronized.

### Client Structure

```typescript
// api/client.ts

import type { paths } from "./types"

const BASE = "/api/v1"

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
    credentials: "include",        // send session cookie
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const error = await res.json()
    throw new ApiError(error.error.code, error.error.message, res.status)
  }
  return res.json()
}

export const api = {
  projects: {
    list: (orgSlug: string) =>
      request<ProjectListResponse>("GET", `/orgs/${orgSlug}/projects`),
    get: (orgSlug: string, id: string) =>
      request<ProjectResponse>("GET", `/orgs/${orgSlug}/projects/${id}`),
    create: (orgSlug: string, body: CreateProjectRequest) =>
      request<ProjectResponse>("POST", `/orgs/${orgSlug}/projects`, body),
    transition: (orgSlug: string, id: string, body: TransitionRequest) =>
      request<void>("POST", `/orgs/${orgSlug}/projects/${id}/transition`, body),
    // ...
  },
  tasks: { /* ... */ },
  channels: { /* ... */ },
  search: { /* ... */ },
  // ...
}
```

The CSRF token is read from the `mc_csrf` cookie and included as a header on every state-changing request, as specified in the security stance document.

---

## Performance Considerations

**Lazy loading:** Route-level code splitting via Vue Router's dynamic imports. Each view is a separate chunk loaded on navigation. The initial bundle contains only the shell layout, auth, and router.

```typescript
// router/index.ts
{ path: "projects", component: () => import("@/views/ProjectBoardView.vue") },
```

**Virtual scrolling:** The event log and chat message lists use virtual scrolling (e.g., `vue-virtual-scroller`) to render only visible items. This handles channels with thousands of messages without DOM bloat.

**Debounced search:** Search API calls are debounced at 300ms. No request is made for queries shorter than 2 characters.

**Image-free design:** The UI uses no decorative images. Avatars are generated as initials on colored backgrounds (derived from the user ID hash). This eliminates image loading latency and keeps the bundle small.

---

## Accessibility

- All interactive elements are keyboard-navigable (tab order, Enter/Space activation).
- Kanban boards support keyboard-based card movement (select card, arrow keys to move between columns, Enter to confirm).
- ARIA labels on dynamic content (live regions for new chat messages and notifications, role attributes on board columns).
- Color is never the sole indicator — priority levels and connection states use both color and icon/text.
- Focus management: modals trap focus, slide-over panels return focus to trigger on close.
- Minimum contrast ratio: 4.5:1 (WCAG AA) for all text.
