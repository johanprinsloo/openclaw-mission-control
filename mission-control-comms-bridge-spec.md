# Mission Control Comms Bridge Plugin

The Comms Bridge is an OpenClaw plugin deployed on OpenClaw host machine(s). It connects OpenClaw agents to Mission Control's communication channels and event system, allowing agents to participate in project channels, receive notifications, and execute commands — all through their existing OpenClaw session model.

## Role in the Architecture

```
┌─────────────────────────────────────────────────────────┐
│  OpenClaw Host                                          │
│                                                         │
│  ┌──────────────┐    ┌─────────────────────────────┐    │
│  │  Agent        │◄──►  OpenClaw Gateway            │    │
│  │  (Claude,     │    │  (session management,       │    │
│  │   other LLMs) │    │   command routing)          │    │
│  └──────────────┘    └──────────┬──────────────────┘    │
│                                 │                       │
│                      ┌──────────▼──────────────────┐    │
│                      │  Comms Bridge Plugin         │    │
│                      │  - SSE listener              │    │
│                      │  - Message relay             │    │
│                      │  - Command router            │    │
│                      │  - Session mapper            │    │
│                      └──────────┬──────────────────┘    │
│                                 │                       │
└─────────────────────────────────┼───────────────────────┘
                                  │  HTTPS
                                  ▼
                      ┌───────────────────────┐
                      │  Mission Control      │
                      │  Server               │
                      │  - REST API           │
                      │  - SSE stream         │
                      │  - WebSocket          │
                      └───────────────────────┘
```

The Comms Bridge is the only component that communicates with Mission Control on behalf of agents. Agents do not connect to Mission Control directly — they interact through the OpenClaw Gateway as usual, and the Comms Bridge translates between the two systems.

## Core Responsibilities

1. **Event Listening:** Maintain a persistent SSE connection to Mission Control per registered agent. Receive real-time events (task assignments, state changes, channel messages, mentions).

2. **Message Relay:** Translate incoming Mission Control channel messages into OpenClaw session messages that agents can process, and translate agent responses back into Mission Control channel posts.

3. **Command Routing:** Intercept OpenClaw commands (`/status`, `/compact`, etc.) sent in Mission Control channels and route them to the appropriate agent's OpenClaw session for execution. Return the command output to the originating channel.

4. **Session Mapping:** Map Mission Control channels to OpenClaw session keys, ensuring that each channel conversation has a persistent context the agent can reference.

5. **Subscription Management:** Automatically manage each agent's SSE subscriptions based on their project assignments in Mission Control.

6. **Sub-Agent Credential Relay:** When a persistent agent spawns a temporary sub-agent via Mission Control's API, the Comms Bridge receives the ephemeral credentials and bootstraps a new OpenClaw session for the sub-agent.

---

## Session Mapping

### Concept

OpenClaw agents operate within sessions — each session has a `sessionKey` that maintains conversation context. Mission Control has channels (org-wide and project-scoped). The Comms Bridge maps between these two models.

### Mapping Rules

| Mission Control Entity | OpenClaw Session Key Format | Notes |
|------------------------|----------------------------|-------|
| Project channel | `mc:{orgSlug}:project:{projectId}` | One session per project per agent. Context accumulates across the project's lifecycle. |
| Org-wide channel | `mc:{orgSlug}:org:{channelId}` | Shared context for cross-project coordination. |
| Sub-agent task | `mc:{orgSlug}:sub:{subAgentId}` | Ephemeral session. Destroyed when the sub-agent is terminated. |

### Session Lifecycle

**Creation:** A session is created the first time an agent receives a message or event for a channel it doesn't yet have a session for. The Comms Bridge fetches recent channel history (last 50 messages via the REST API) and injects it as session context before delivering the triggering message.

**Persistence:** Sessions persist across Comms Bridge restarts. Session keys and their metadata (last message ID, channel ID, agent ID) are stored in a local SQLite database on the OpenClaw host. On restart, the Comms Bridge reconnects SSE streams and resumes from the last known event ID.

**Destruction:** Project channel sessions are destroyed when the agent is unassigned from the project. Sub-agent sessions are destroyed when the sub-agent is terminated. Org-wide channel sessions persist indefinitely.

---

## Message Flow

### Inbound: Mission Control → Agent

```
1. Mission Control emits event via SSE
   (e.g., message.created in a project channel)

2. Comms Bridge SSE listener receives the event

3. Bridge checks: is this agent subscribed to this channel?
   - No  → discard
   - Yes → continue

4. Bridge resolves the OpenClaw session key for this channel

5. Bridge formats the message for the agent:
   {
     "source": "mission-control",
     "channel": "mc:acme:project:prj_xyz789",
     "sender": "Jane (human)",
     "content": "Can you review the PR for the auth module?",
     "mentions_me": true,
     "context": {
       "project": "Mission Control API",
       "task": null,
       "channel_type": "project"
     }
   }

6. Bridge delivers the message to the agent's OpenClaw session
   via the Gateway's internal message API

7. Agent processes and (optionally) responds

8. Bridge picks up the agent's response from the Gateway
   and posts it to Mission Control via:
   POST /api/v1/orgs/{orgSlug}/channels/{channelId}/messages
```

### Outbound: Agent → Mission Control

```
1. Agent produces a message in an OpenClaw session
   that is mapped to a Mission Control channel

2. Gateway notifies the Comms Bridge of the outbound message

3. Bridge resolves the channel ID from the session key

4. Bridge posts the message to Mission Control:
   POST /api/v1/orgs/{orgSlug}/channels/{channelId}/messages
   {
     "content": "PR reviewed. Found 2 issues, posted comments on GitHub.",
     "mentions": []
   }

5. The agent's API key authenticates the request.
   Mission Control attributes the message to the agent.
```

### Command Flow: /status, /compact, etc.

```
1. A human (or another agent) posts a command in a Mission Control channel:
   "/status prj_xyz789"

2. Mission Control server detects the leading slash and emits a
   command.invoked event via SSE (in addition to storing it as a message)

3. Comms Bridge receives the event and identifies the target agent
   based on channel membership and command routing rules

4. Bridge translates the command into an OpenClaw Gateway command:
   - /status  → Gateway /status command for the project session
   - /compact → Gateway /compact command for the project session

5. Gateway executes the command and returns output to the Bridge

6. Bridge posts the command output to the originating Mission Control channel
   as a message from the agent
```

---

## Agent Registration

### Persistent Agents

Each persistent OpenClaw agent that should participate in Mission Control is registered in the Comms Bridge configuration:

```yaml
# comms-bridge.yaml
mission_control:
  url: "https://mc.openclaw.dev"

agents:
  - name: "builder-agent-01"
    api_key_env: "MC_API_KEY_BUILDER_01"    # API key stored in env var, not config
    org_slug: "acme-robotics"
    auto_subscribe: true                     # auto-subscribe to all assigned projects
```

On startup, the Comms Bridge:

1. Validates each agent's API key against Mission Control (`GET /api/v1/orgs/{orgSlug}/users`).
2. Fetches the agent's project assignments (`GET /api/v1/orgs/{orgSlug}/projects?assigned_to=me`).
3. Sets subscriptions for all assigned project channels and the org-wide channel (`PUT /api/v1/orgs/{orgSlug}/subscriptions`).
4. Opens a persistent SSE connection (`GET /api/v1/orgs/{orgSlug}/events/stream`).
5. Resumes from the last known event ID (if restarting).

### Dynamic Registration

When a persistent agent is assigned to a new project in Mission Control (via the API or UI), the Comms Bridge:

1. Receives a `project.user_assigned` event via the existing SSE stream.
2. Updates subscriptions to include the new project's channel.
3. Creates the session mapping for the new channel.
4. Fetches recent channel history and primes the session context.

When an agent is unassigned, the reverse occurs: subscription removed, session archived.

---

## Sub-Agent Lifecycle

### Spawning

```
1. Persistent agent (or human) calls:
   POST /api/v1/orgs/{orgSlug}/sub-agents
   {
     "task_id": "tsk_abc123",
     "model": "claude-sonnet-4-5-20250514",
     "instructions": "Review the PR and post findings.",
     "timeout_minutes": 30
   }

2. Mission Control returns ephemeral credentials:
   { "id": "sa_tmp_xyz", "ephemeral_api_key": "mc_ak_tmp_..." }

3. Comms Bridge receives sub_agent.created event via SSE

4. Bridge bootstraps a new OpenClaw session:
   - Session key: mc:acme:sub:sa_tmp_xyz
   - Injects task details and instructions as initial context
   - Configures the session with the specified model

5. Bridge opens a scoped SSE connection (or adds subscriptions)
   for the sub-agent's task channel

6. Sub-agent begins executing within its OpenClaw session
```

### Termination

```
1. Sub-agent completes work, or timeout expires, or a user terminates it:
   POST /api/v1/orgs/{orgSlug}/sub-agents/{subAgentId}/terminate

2. Mission Control revokes the ephemeral API key and emits
   sub_agent.terminated event

3. Comms Bridge receives the event and:
   - Closes any SSE/subscription state for the sub-agent
   - Archives the OpenClaw session (context preserved for audit)
   - Removes the session mapping from local state
```

---

## Connection Management

### SSE Reconnection

SSE connections are long-lived and will drop due to network issues, server restarts, or deployment rollouts. The Comms Bridge handles this automatically:

- **Reconnection:** Exponential backoff starting at 1 second, capped at 60 seconds. Uses the `Last-Event-ID` header to resume from the last received event, avoiding message loss.
- **Heartbeat monitoring:** Mission Control sends SSE heartbeat comments (`: heartbeat`) every 30 seconds. If no data (including heartbeats) is received for 90 seconds, the Bridge treats the connection as dead and reconnects.
- **Graceful degradation:** If SSE is unavailable for an extended period (>5 minutes), the Bridge logs a warning and switches to polling the events API every 30 seconds until SSE reconnects. It posts a notification to the org-wide channel alerting that real-time delivery is degraded.

### REST Fallback for Messaging

The Comms Bridge uses REST (`POST /channels/{channelId}/messages`) for all outbound messages rather than WebSocket. This is a deliberate choice:

- REST is stateless and simpler to retry on failure.
- The Bridge already maintains an SSE connection for inbound events — adding a WebSocket would mean two persistent connections per agent.
- Outbound message volume from agents is low enough that REST latency is negligible.

WebSocket is reserved for the Web UI where bidirectional real-time chat justifies the connection overhead.

### Local State Storage

The Comms Bridge maintains a small SQLite database on the OpenClaw host:

```
bridge_state.db

session_mappings
  session_key     TEXT PRIMARY KEY
  agent_id        TEXT NOT NULL
  org_slug        TEXT NOT NULL
  channel_id      TEXT NOT NULL
  channel_type    TEXT NOT NULL          -- project | org_wide | sub_agent
  created_at      TIMESTAMPTZ NOT NULL

event_cursors
  agent_id        TEXT PRIMARY KEY
  org_slug        TEXT NOT NULL
  last_event_id   TEXT NOT NULL          -- last SSE event ID received
  updated_at      TIMESTAMPTZ NOT NULL
```

This enables the Bridge to resume cleanly after a restart without re-fetching full channel histories.

---

## Configuration

### Full Configuration Reference

```yaml
# comms-bridge.yaml

mission_control:
  url: "https://mc.openclaw.dev"          # Mission Control server URL
  verify_tls: true                         # TLS certificate verification
  request_timeout_seconds: 30              # Timeout for REST API calls
  sse_heartbeat_interval_seconds: 30       # Expected heartbeat frequency
  sse_heartbeat_timeout_seconds: 90        # Reconnect if no data received

gateway:
  url: "http://localhost:8080"             # OpenClaw Gateway URL (local)
  api_key_env: "OPENCLAW_GATEWAY_KEY"      # Gateway authentication

agents:
  - name: "builder-agent-01"
    api_key_env: "MC_API_KEY_BUILDER_01"
    org_slug: "acme-robotics"
    auto_subscribe: true
    history_fetch_count: 50                # Messages to fetch when priming a new session

  - name: "reviewer-agent-02"
    api_key_env: "MC_API_KEY_REVIEWER_02"
    org_slug: "acme-robotics"
    auto_subscribe: true

state:
  db_path: "./data/bridge_state.db"        # Local SQLite state database

logging:
  level: "info"                            # debug | info | warning | error
  format: "json"                           # json | text
```

### Environment Variables

API keys are never stored in the configuration file. They are referenced by environment variable name and loaded from a separate secrets file (see Security Considerations):

```
/etc/openclaw/mc-bridge.secrets    (permissions: 0600)
```

```bash
MC_API_KEY_BUILDER_01="mc_ak_live_..."
MC_API_KEY_REVIEWER_02="mc_ak_live_..."
OPENCLAW_GATEWAY_KEY="gw_..."
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| SSE connection lost | Exponential backoff reconnection with `Last-Event-ID` resume |
| SSE unavailable >5 min | Fall back to REST polling; post degradation notice to org channel |
| Outbound message fails (5xx) | Retry 3 times with exponential backoff, then log error and post failure notice to agent's session |
| Outbound message fails (4xx) | Do not retry. Log error with full context. 401/403 triggers an API key validation check. |
| Agent API key revoked/rotated | SSE connection returns 401. Bridge stops the agent, logs error, and posts alert to local OpenClaw admin channel. Requires config update and restart. |
| Mission Control returns 429 | Respect `Retry-After` header. Queue outbound messages in memory (bounded buffer, 1000 messages max). Drop oldest if buffer fills. |
| Sub-agent spawn fails | Log error. Notify the requesting agent/user in the originating channel with the error detail. |
| Gateway unreachable | Queue inbound messages in memory (bounded buffer). Retry Gateway delivery with backoff. Alert after 2 minutes of consecutive failures. |
| Local SQLite write fails | Log critical error. Continue operating with in-memory state (session mappings and cursors). Attempt SQLite recovery on next write. |

---

## Monitoring

The Comms Bridge exposes a local HTTP health endpoint and metrics:

### Health Check

```
GET http://localhost:9090/health
```

```json
{
  "status": "healthy",
  "agents": [
    {
      "name": "builder-agent-01",
      "org": "acme-robotics",
      "sse_connected": true,
      "last_event_at": "2026-02-13T10:20:00Z",
      "active_sessions": 4
    }
  ],
  "gateway_reachable": true,
  "mission_control_reachable": true
}
```

### Metrics (Prometheus)

| Metric | Type | Description |
|--------|------|-------------|
| `bridge_sse_connections_active` | Gauge | Number of active SSE connections |
| `bridge_sse_reconnections_total` | Counter | Total SSE reconnection attempts |
| `bridge_messages_inbound_total` | Counter | Messages received from Mission Control |
| `bridge_messages_outbound_total` | Counter | Messages sent to Mission Control |
| `bridge_messages_outbound_errors_total` | Counter | Failed outbound message deliveries |
| `bridge_commands_routed_total` | Counter | OpenClaw commands routed from MC channels |
| `bridge_sub_agents_active` | Gauge | Currently active sub-agents managed by this Bridge |
| `bridge_gateway_latency_seconds` | Histogram | Gateway message delivery latency |
| `bridge_mc_api_latency_seconds` | Histogram | Mission Control API call latency |

Metrics are exposed at `http://localhost:9090/metrics` in Prometheus format, scrapable by the same Prometheus instance monitoring Mission Control.

---

## Implementation Language

The Comms Bridge is implemented in **Python**, consistent with the Mission Control server stack. It reuses:

- **httpx** for async HTTP (REST calls to Mission Control and the Gateway).
- **aiohttp** or **httpx-sse** for SSE client connections.
- **aiosqlite** for local state persistence.
- **structlog** for structured logging (same format as Mission Control server).
- **Pydantic** for configuration validation.

The plugin is packaged as a standalone Python package installable via pip:

```bash
pip install openclaw-mc-bridge
```

It runs as a long-lived process alongside the OpenClaw Gateway, managed by systemd or as a Docker container in the OpenClaw host's compose stack.

---

## Updates and Lifecycle Management

### Update Mechanisms

The Comms Bridge supports three update paths. All three result in the same outcome — new version installed, process restarted gracefully.

**`openclaw update` (recommended).** The OpenClaw CLI checks for new versions of all installed plugins, including the Comms Bridge. If an update is available:

1. CLI downloads the new package version.
2. CLI sends a graceful shutdown signal to the running Bridge process.
3. Bridge executes the shutdown sequence (see below).
4. CLI installs the update (`pip install --upgrade openclaw-mc-bridge`).
5. CLI restarts the Bridge process.
6. Bridge resumes from the persisted event cursor.

This is the primary update path for self-hosted deployments. It requires no SSH access or manual intervention beyond running the command — which can itself be triggered by an agent or scheduled via cron.

**Docker-based.** For hosts running the Bridge as a Docker container:

```bash
docker compose pull mc-bridge
docker compose up -d mc-bridge
```

Docker sends SIGTERM to the running container, which triggers the graceful shutdown sequence. The new container starts and resumes from the SQLite state database (mounted as a volume). `openclaw update` can wrap this automatically when it detects a Docker-based installation.

**Manual pip upgrade.** For advanced users or development environments:

```bash
pip install --upgrade openclaw-mc-bridge
systemctl restart openclaw-mc-bridge    # or equivalent process manager command
```

### Graceful Shutdown Sequence

When the Bridge receives SIGTERM (or SIGINT):

```
1. Stop accepting new inbound SSE events
   (close SSE connections cleanly)

2. Flush outbound message queue
   (deliver any queued messages to Mission Control via REST,
    retry up to 3 times, then log and discard on failure)

3. Persist final event cursors to SQLite
   (last_event_id per agent, ensuring no gap on restart)

4. Archive any active sub-agent session state
   (sub-agents continue running in Mission Control;
    the Bridge will re-attach on restart)

5. Close Gateway connections

6. Exit
```

Target shutdown time: under 10 seconds. If flush/persist takes longer than 15 seconds, the Bridge force-exits and logs a warning. On restart, it may re-process a small number of events (idempotent handling at the agent session level prevents duplicates).

### Version Compatibility

The Bridge includes a version compatibility check on startup. It calls `GET /api/v1/orgs/{orgSlug}` and reads the `X-MC-API-Version` header from the response. If the Mission Control server's API version is newer than what the Bridge supports, it logs a warning and continues (additive API changes are backward-compatible). If the API version indicates a breaking change the Bridge doesn't support, it refuses to start and logs an error with the required Bridge version.

This prevents silent failures when the Mission Control server is updated but the Bridge is not (or vice versa).

### Auto-Update (Optional)

For hosted environments or hands-off self-hosted deployments, the Bridge can be configured to check for updates on a schedule and apply them automatically:

```yaml
# comms-bridge.yaml
updates:
  auto_check: true                         # check for new versions periodically
  check_interval_hours: 24                 # how often to check
  auto_apply: false                        # if true, update and restart without prompting
  notify_channel: "org_wide"               # post update availability notices to this channel
```

When `auto_check` is enabled and a new version is found, the Bridge posts a message to the configured channel:

> "Comms Bridge v1.3.0 is available (currently running v1.2.1). Run `openclaw update` to apply, or enable auto_apply in bridge configuration."

When `auto_apply` is also enabled, the Bridge triggers its own graceful restart cycle during a low-activity window (configurable, default: 03:00 local time).

---

## Security Considerations

### Credential Storage

API keys are loaded from environment variables at runtime, but those variables must be sourced from persistent storage that survives reboots and updates. The configuration file (`comms-bridge.yaml`) references keys by environment variable name — it never contains the key values themselves. This separation allows the config to be version-controlled and shared without exposing credentials.

The keys are persisted in a **secrets file** with restricted filesystem permissions:

```
/etc/openclaw/mc-bridge.secrets
```

```bash
# /etc/openclaw/mc-bridge.secrets
# Permissions: 0600 (owner read/write only)
# Owner: the service account running the Bridge

MC_API_KEY_BUILDER_01="mc_ak_live_..."
MC_API_KEY_REVIEWER_02="mc_ak_live_..."
OPENCLAW_GATEWAY_KEY="gw_..."
```

How this file is loaded depends on the deployment method:

| Deployment | Mechanism | Notes |
|------------|-----------|-------|
| Docker | `env_file: /etc/openclaw/mc-bridge.secrets` in docker-compose.yml | File is outside the container, mounted at runtime. Survives image updates. |
| Systemd | `EnvironmentFile=/etc/openclaw/mc-bridge.secrets` in the unit file | Loaded on service start. Survives reboots. |
| Manual / dev | `source /etc/openclaw/mc-bridge.secrets` before starting the process | Developer's responsibility to source before running. |

**Key lifecycle:**

- **Initial provisioning:** When an agent is registered in Mission Control, the Admin receives the API key once. The Admin (or `openclaw setup`) writes it to the secrets file.
- **Rotation:** When an Admin rotates an API key in Mission Control (`POST .../api-keys/rotate`), the new key must be written to the secrets file and the Bridge restarted. `openclaw update` should detect rotated keys that haven't been applied and warn the operator.
- **Revocation:** When a key is revoked, the Bridge's SSE connection will receive a 401. The Bridge stops the affected agent and logs an error. The operator removes the old key from the secrets file.

**For hosted or higher-security environments**, the secrets file can be replaced with a secrets manager (AWS Secrets Manager, HashiCorp Vault). The Bridge supports a pluggable credential provider:

```yaml
# comms-bridge.yaml
credentials:
  provider: "env"               # env (default) | aws_secrets_manager | vault
  # AWS Secrets Manager example:
  # provider: "aws_secrets_manager"
  # secret_name: "openclaw/mc-bridge/api-keys"
  # region: "us-east-1"
```

When using a secrets manager, the Bridge fetches credentials on startup and caches them in memory. No secrets file is needed on disk.

### Other Security Controls

- **TLS required.** The Bridge refuses to connect to Mission Control over plain HTTP unless `verify_tls: false` is explicitly set (intended only for local development).
- **Credentials never logged.** API keys are masked in all log output, error messages, and health check responses. The Bridge logs the key prefix only (e.g., `mc_ak_live_...`).
- **Local state contains no secrets.** The SQLite database stores session mappings and event cursors but never API keys or message content. If message content caching is added in the future, at-rest encryption should be implemented.
- **Gateway communication.** The Bridge communicates with the local Gateway over localhost. If the Gateway is on a separate host, TLS must be configured for this link as well.
- **No inbound network exposure.** The Bridge makes only outbound connections to Mission Control and the local Gateway. The health/metrics endpoint binds to localhost by default and should not be exposed externally without authentication.


##Key design decisions to review:

Agents never connect to Mission Control directly. The Bridge is the single integration point. This means agents don't need to know about Mission Control's API — they interact through their normal OpenClaw sessions, and the Bridge handles translation. This keeps the agent-side simple and means you can change Mission Control's API without touching agent code.

SSE for inbound, REST for outbound. The Bridge maintains one SSE connection per agent for receiving events, but uses plain REST for posting messages back. This avoids the complexity of managing both SSE and WebSocket connections from the Bridge, and outbound agent message volume is low enough that REST latency doesn't matter.

Local SQLite for state persistence. Session mappings and event cursors survive Bridge restarts without depending on an external database. This is important for self-hosted deployments where the Bridge runs alongside the Gateway on a single machine. The SQLite DB stores only metadata — no message content or credentials.

Session priming with channel history. When an agent first encounters a channel, the Bridge fetches the last 50 messages and injects them as session context. This gives the agent conversational continuity without requiring it to have been listening from the start.

Command routing is event-driven. When someone types /status in a Mission Control channel, the server emits a command.invoked event. The Bridge picks it up, routes it to the correct agent's Gateway session, and posts the output back. This means command execution happens in OpenClaw (where the agent has full context), not in Mission Control.

Graceful degradation with polling fallback. If SSE drops for more than 5 minutes, the Bridge switches to polling and posts a degradation notice. This avoids silent message loss during extended outages.

One thing to flag: the spec assumes the OpenClaw Gateway has an internal API for injecting messages into agent sessions. If that API doesn't exist yet, it would need to be built as a prerequisite. Worth confirming.
