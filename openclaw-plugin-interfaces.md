# OpenClaw Plugin Interfaces

This document describes the OpenClaw plugin system and Gateway APIs relevant to implementing the Mission Control Comms Bridge. It serves as a reference for how external systems integrate with OpenClaw agents.

## Overview

OpenClaw supports plugins that extend the Gateway with:
- Agent tools (JSON-schema functions callable by LLMs)
- Gateway RPC methods (custom WebSocket commands)
- Background services (long-running processes)
- CLI commands
- Channel plugins (messaging integrations like Signal, Telegram, etc.)

Plugins run **in-process** with the Gateway and are loaded at startup. They communicate with agents through the Gateway's session management system.

---

## Plugin Structure

### Manifest (`openclaw.plugin.json`)

Every plugin **must** include a manifest file in its root directory:

```json
{
  "id": "mc-bridge",
  "name": "Mission Control Comms Bridge",
  "description": "Connects OpenClaw agents to Mission Control channels",
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "missionControlUrl": { "type": "string" },
      "agents": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string" },
            "apiKeyEnv": { "type": "string" },
            "orgSlug": { "type": "string" }
          },
          "required": ["name", "apiKeyEnv", "orgSlug"]
        }
      }
    },
    "required": ["missionControlUrl", "agents"]
  },
  "uiHints": {
    "missionControlUrl": { "label": "Mission Control URL", "placeholder": "https://mc.openclaw.dev" },
    "agents": { "label": "Registered Agents" }
  }
}
```

**Required fields:**
- `id` (string): Canonical plugin identifier.
- `configSchema` (object): JSON Schema for plugin configuration.

**Optional fields:**
- `name`, `description`: Display metadata.
- `channels` (array): Channel IDs registered by this plugin.
- `skills` (array): Skill directories to load.
- `uiHints` (object): UI labels, placeholders, and sensitive field markers.

### Plugin Entry Point

Plugins export either a function or an object:

```typescript
// Function form
export default function (api: OpenClawPluginApi) {
  // Register tools, services, RPC methods, etc.
}

// Object form (preferred for complex plugins)
export default {
  id: "mc-bridge",
  name: "Mission Control Comms Bridge",
  configSchema: { /* ... */ },
  register(api: OpenClawPluginApi) {
    // Registration logic
  },
};
```

---

## Plugin API (`OpenClawPluginApi`)

The `api` object passed to plugins provides registration methods and runtime access.

### Core Registration Methods

```typescript
interface OpenClawPluginApi {
  // Configuration
  config: OpenClawConfig;          // Current gateway configuration
  logger: PluginLogger;            // Structured logger for the plugin

  // Registration
  registerTool(tool: ToolDefinition, options?: { optional: boolean }): void;
  registerGatewayMethod(method: string, handler: RpcHandler): void;
  registerService(service: ServiceDefinition): void;
  registerCli(setup: CliSetup, options?: { commands: string[] }): void;
  registerChannel(channel: { plugin: ChannelPlugin }): void;
  registerCommand(command: CommandDefinition): void;
  registerProvider(provider: ProviderDefinition): void;

  // Runtime helpers
  runtime: PluginRuntime;
}
```

### Background Services

The Comms Bridge will run as a **background service** — a long-running process that maintains SSE connections and relays messages:

```typescript
api.registerService({
  id: "mc-bridge",
  
  async start() {
    // Called when Gateway starts
    // Initialize SSE connections, load state, etc.
    api.logger.info("Mission Control Comms Bridge starting");
  },
  
  async stop() {
    // Called on Gateway shutdown (SIGTERM)
    // Flush queues, persist state, close connections
    api.logger.info("Mission Control Comms Bridge stopping");
  },
});
```

Services are started after the Gateway initializes and stopped gracefully on shutdown.

### Gateway RPC Methods

Plugins can register custom RPC methods accessible via the Gateway WebSocket:

```typescript
api.registerGatewayMethod("mc-bridge.status", ({ respond, params }) => {
  // Return health/status information
  respond(true, {
    connected: true,
    agents: [
      { name: "builder-agent-01", sseConnected: true, activeSessions: 4 }
    ]
  });
});

api.registerGatewayMethod("mc-bridge.relay", async ({ respond, params }) => {
  // Custom method for message relay (if needed)
  const { sessionKey, message } = params;
  // ... relay logic ...
  respond(true, { delivered: true });
});
```

RPC methods are called via the Gateway WebSocket protocol (see below).

---

## Plugin Runtime (`api.runtime`)

The runtime provides access to core Gateway functionality without importing internal modules directly.

### Key Runtime Interfaces

```typescript
interface PluginRuntime {
  // Text processing
  channel: {
    text: {
      chunkMarkdownText(text: string, limit: number): string[];
      resolveTextChunkLimit(cfg: OpenClawConfig, channel: string): number;
    };
    
    // Message routing
    routing: {
      resolveAgentRoute(params: {
        cfg: OpenClawConfig;
        channel: string;
        accountId: string;
        peer: { kind: string; id: string };
      }): { sessionKey: string; accountId: string };
    };
    
    // Media handling
    media: {
      fetchRemoteMedia(params: { url: string }): Promise<{ buffer: Buffer; contentType?: string }>;
      saveMediaBuffer(buffer: Uint8Array, contentType: string | undefined, direction: string, maxBytes: number): Promise<{ path: string }>;
    };
    
    // Group/mention handling
    groups: {
      resolveGroupPolicy(cfg: OpenClawConfig, channel: string, accountId: string, groupId: string): { allowed: boolean };
    };
    mentions: {
      buildMentionRegexes(cfg: OpenClawConfig, agentId?: string): RegExp[];
      matchesMentionPatterns(text: string, regexes: RegExp[]): boolean;
    };
  };
  
  // Logging
  logging: {
    shouldLogVerbose(): boolean;
    getChildLogger(name: string): PluginLogger;
  };
  
  // State persistence
  state: {
    resolveStateDir(cfg: OpenClawConfig): string;
  };
  
  // TTS (if needed)
  tts: {
    textToSpeechTelephony(params: { text: string; cfg: OpenClawConfig }): Promise<{ buffer: Buffer; sampleRate: number }>;
  };
}
```

---

## Gateway WebSocket Protocol

The Gateway exposes a WebSocket control plane that plugins and external clients can use. This is the primary interface for injecting messages into agent sessions.

### Connection

```
ws://localhost:8080/gateway/ws
wss://gateway.example.com/gateway/ws
```

### Handshake

1. **Server sends challenge:**
```json
{
  "type": "event",
  "event": "connect.challenge",
  "payload": { "nonce": "...", "ts": 1737264000000 }
}
```

2. **Client sends connect request:**
```json
{
  "type": "req",
  "id": "1",
  "method": "connect",
  "params": {
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
      "id": "mc-bridge",
      "version": "1.0.0",
      "platform": "linux",
      "mode": "operator"
    },
    "role": "operator",
    "scopes": ["operator.read", "operator.write"],
    "auth": { "token": "..." },
    "device": {
      "id": "mc-bridge-host-fingerprint",
      "publicKey": "...",
      "signature": "...",
      "signedAt": 1737264000000,
      "nonce": "..."
    }
  }
}
```

3. **Server responds:**
```json
{
  "type": "res",
  "id": "1",
  "ok": true,
  "payload": {
    "type": "hello-ok",
    "protocol": 3,
    "policy": { "tickIntervalMs": 15000 }
  }
}
```

### Roles and Scopes

| Role | Description |
|------|-------------|
| `operator` | Control plane client (CLI, UI, automation, **Comms Bridge**) |
| `node` | Capability host (camera, screen, canvas, system.run) |

**Operator scopes:**
- `operator.read` — Read status, sessions, config
- `operator.write` — Send messages, modify sessions
- `operator.admin` — Administrative operations
- `operator.approvals` — Exec approval handling
- `operator.pairing` — Device pairing management

### Frame Types

**Request:**
```json
{ "type": "req", "id": "unique-id", "method": "method.name", "params": { ... } }
```

**Response:**
```json
{ "type": "res", "id": "unique-id", "ok": true, "payload": { ... } }
// or
{ "type": "res", "id": "unique-id", "ok": false, "error": { "code": "...", "message": "..." } }
```

**Event (server → client):**
```json
{ "type": "event", "event": "event.name", "payload": { ... }, "seq": 123 }
```

### Key Gateway Methods for Comms Bridge

The following built-in Gateway methods are relevant for the Comms Bridge:

#### Session Management

```typescript
// List active sessions
{ "method": "sessions.list", "params": { "filter": { "agent": "main" } } }

// Get session history
{ "method": "sessions.history", "params": { "sessionKey": "mc:acme:project:prj_xyz" } }

// Send message to a session (inject message as if from a channel)
{ "method": "sessions.send", "params": {
    "sessionKey": "mc:acme:project:prj_xyz",
    "message": "Review the PR for the auth module",
    "context": {
      "source": "mission-control",
      "sender": "Jane (human)",
      "channel": "project-channel"
    }
  }
}
```

#### Agent Control

```typescript
// Get agent status
{ "method": "agent.status", "params": { "agentId": "main" } }

// Wake agent (trigger processing)
{ "method": "agent.wake", "params": { "sessionKey": "mc:acme:project:prj_xyz" } }
```

#### Chat/Messaging

```typescript
// Subscribe to session events
{ "method": "chat.subscribe", "params": { "sessionKey": "mc:acme:project:prj_xyz" } }

// Receive chat events (server → client)
{ "type": "event", "event": "chat.message", "payload": {
    "sessionKey": "mc:acme:project:prj_xyz",
    "role": "assistant",
    "content": "PR reviewed. Found 2 issues..."
  }
}
```

---

## Session Model

OpenClaw agents operate within **sessions** — each session has a unique `sessionKey` that maintains conversation context and history.

### Session Key Format

Session keys follow the pattern: `{source}:{identifiers}`

Examples:
- `signal:dm:+14155551234` — Signal DM session
- `telegram:group:123456789` — Telegram group session
- `mc:acme:project:prj_xyz789` — Mission Control project channel (proposed)

### Session Lifecycle

1. **Creation:** Sessions are created on first message. The Gateway initializes context and begins tracking history.

2. **Persistence:** Session history is stored locally (SQLite) and survives Gateway restarts.

3. **Compaction:** Long sessions are periodically compacted to manage context window limits.

4. **Archival:** Sessions can be archived (history preserved, no longer active).

### Injecting Messages into Sessions

The primary mechanism for the Comms Bridge to deliver Mission Control messages to agents:

```typescript
// Via Gateway WebSocket RPC
{
  "type": "req",
  "id": "msg-001",
  "method": "sessions.send",
  "params": {
    "sessionKey": "mc:acme:project:prj_xyz",
    "message": "Can you review the PR for the auth module?",
    "metadata": {
      "source": "mission-control",
      "channel": "project-channel",
      "sender": {
        "id": "usr_jane123",
        "name": "Jane",
        "type": "human"
      },
      "mentionsAgent": true
    }
  }
}
```

The Gateway processes this as an inbound message, adds it to session history, and triggers agent processing.

### Receiving Agent Responses

After subscribing to a session, the Bridge receives events when the agent responds:

```typescript
// Subscribe to session
{ "method": "chat.subscribe", "params": { "sessionKey": "mc:acme:project:prj_xyz" } }

// Agent response event
{
  "type": "event",
  "event": "chat.message",
  "payload": {
    "sessionKey": "mc:acme:project:prj_xyz",
    "role": "assistant",
    "content": "PR reviewed. Found 2 issues, posted comments on GitHub.",
    "timestamp": "2026-02-14T10:16:00Z"
  }
}
```

The Bridge then posts this response to the corresponding Mission Control channel via REST.

---

## Implementation Approach for Comms Bridge

Based on the plugin interfaces, the Comms Bridge can be implemented in two ways:

### Option A: In-Process Plugin (Recommended)

The Bridge runs as an OpenClaw plugin, loaded by the Gateway at startup:

```typescript
// packages/bridge/src/index.ts
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

export default {
  id: "mc-bridge",
  name: "Mission Control Comms Bridge",
  configSchema: { /* ... */ },
  
  register(api: OpenClawPluginApi) {
    const bridge = new CommsBridge(api);
    
    // Register as background service
    api.registerService({
      id: "mc-bridge",
      start: () => bridge.start(),
      stop: () => bridge.stop(),
    });
    
    // Register status RPC
    api.registerGatewayMethod("mc-bridge.status", ({ respond }) => {
      respond(true, bridge.getStatus());
    });
  },
};
```

**Advantages:**
- Direct access to `api.runtime` helpers
- In-process communication (no network overhead to Gateway)
- Participates in Gateway lifecycle (graceful shutdown)
- Configuration validated via manifest schema

**Disadvantages:**
- Must be TypeScript/JavaScript
- Runs in Gateway process (crash affects Gateway)

### Option B: External Process via WebSocket

The Bridge runs as a separate process and connects to the Gateway via WebSocket:

```python
# packages/bridge/openclaw_mc_bridge/gateway_client.py
import websockets
import json

class GatewayClient:
    async def connect(self, url: str, token: str):
        self.ws = await websockets.connect(url)
        # Complete handshake...
        await self._authenticate(token)
    
    async def send_to_session(self, session_key: str, message: str, metadata: dict):
        await self.ws.send(json.dumps({
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "sessions.send",
            "params": {
                "sessionKey": session_key,
                "message": message,
                "metadata": metadata
            }
        }))
        # Wait for response...
    
    async def subscribe_session(self, session_key: str):
        await self.ws.send(json.dumps({
            "type": "req",
            "id": str(uuid.uuid4()),
            "method": "chat.subscribe",
            "params": { "sessionKey": session_key }
        }))
```

**Advantages:**
- Language-agnostic (Python implementation matches MC server stack)
- Process isolation (Bridge crash doesn't affect Gateway)
- Can run on separate host

**Disadvantages:**
- Network latency to Gateway
- Must implement WebSocket protocol client
- Separate process management (systemd, Docker)

### Recommendation

**Use Option B (External Process)** for the following reasons:

1. **Stack consistency:** Mission Control server is Python; the Bridge should match.
2. **Isolation:** A bug in the Bridge shouldn't crash the Gateway.
3. **Deployment flexibility:** Bridge can run on a different host than the Gateway.
4. **Existing spec:** The Comms Bridge spec already assumes a separate Python process.

The Bridge connects to the Gateway via WebSocket as an `operator` with `read` and `write` scopes, uses `sessions.send` to inject messages, and subscribes to sessions to receive agent responses.

---

## Configuration

### Gateway Configuration for External Bridge

```json5
// ~/.openclaw/openclaw.json
{
  "gateway": {
    // Enable WebSocket control plane (usually enabled by default)
    "controlPlane": {
      "enabled": true,
      "bind": "127.0.0.1:8080"
    },
    
    // Authentication token for the Bridge
    "token": "${OPENCLAW_GATEWAY_TOKEN}"
  }
}
```

### Bridge Configuration

```yaml
# comms-bridge.yaml
gateway:
  url: "ws://localhost:8080/gateway/ws"
  token_env: "OPENCLAW_GATEWAY_TOKEN"

mission_control:
  url: "https://mc.openclaw.dev"

agents:
  - name: "builder-agent-01"
    api_key_env: "MC_API_KEY_BUILDER_01"
    org_slug: "acme-robotics"
```

---

## Summary

| Interface | Use Case for Comms Bridge |
|-----------|---------------------------|
| Plugin Manifest | Not needed if running as external process |
| Plugin API | Not needed if running as external process |
| Gateway WebSocket Protocol | **Primary interface** — connect, authenticate, send/receive messages |
| `sessions.send` RPC | Inject Mission Control messages into agent sessions |
| `chat.subscribe` RPC | Receive agent responses for relay to Mission Control |
| Session Keys | Map MC channels to OpenClaw sessions (`mc:{org}:{type}:{id}`) |

The Comms Bridge connects to the Gateway as an operator client, manages session mappings in local SQLite, and bidirectionally relays messages between Mission Control channels and OpenClaw agent sessions.
