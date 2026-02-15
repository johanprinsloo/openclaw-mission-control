# POC-6: Comms Bridge ↔ Mission Control Round-Trip — Results

## Date
2026-02-15

## Objective
Prove end-to-end message and command flow: MC Channel → Bridge (SSE) → Mock Gateway → Bridge (REST) → MC Channel. Validate SQLite-based session mapping and cursor resume.

## Architecture

```
Human User
    │
    ▼  POST /channels/{id}/messages
┌──────────────┐   SSE stream    ┌──────────────┐   POST /v1/chat   ┌──────────────┐
│  MC Server   │ ──────────────► │    Bridge     │ ────────────────► │ Mock Gateway │
│  (port 8100) │ ◄────────────── │  (SQLite)     │ ◄──────────────── │  (port 8200) │
│  SQLite      │  POST /messages │              │   JSON response   │              │
└──────────────┘                 └──────────────┘                   └──────────────┘
```

## Components

| Component | File | Port | Purpose |
|-----------|------|------|---------|
| MC Server | `mc_server.py` | 8100 | Channels, messages, SSE stream with sequence_id replay |
| Mock Gateway | `mock_gateway.py` | 8200 | Canned agent chat + command responses |
| Comms Bridge | `bridge.py` | — | SSE listener, session mapper, event→REST loop |
| Test Script | `test_roundtrip.py` | — | Automated acceptance tests |

## Acceptance Criteria Results

| Criteria | Result | Notes |
|----------|--------|-------|
| Message posted in MC → arrives at Gateway within 2s | ✅ PASS | Sub-second via SSE push |
| Gateway response → appears in MC channel within 2s | ✅ PASS | ~100ms total round-trip |
| `/status` command → routed → output posted within 3s | ✅ PASS | Sub-second |
| Session mapping persisted in SQLite | ✅ PASS | `mc:{org}:project:{channel_id}` format |
| Bridge restart resumes from last event cursor | ✅ PASS | Cursor 4 → 6 after restart, missed msg processed |
| SSE reconnection delivers missed events | ✅ PASS | `Last-Event-ID` header, DB replay |

## Key Findings

1. **SSE → REST round-trip latency is negligible** for interactive chat. The bottleneck will be the real LLM, not the transport.

2. **SQLite is perfectly adequate** for Bridge state. Two tables (session_mappings, event_cursors) cover all needs. No need for Redis on the Bridge side.

3. **Session mapping model works cleanly.** The `mc:{orgSlug}:project:{channelId}` key format maps directly to the spec. One row per channel per agent.

4. **Cursor-based SSE resume is robust.** The Bridge stores `last_sequence_id` after each event. On restart, it passes `Last-Event-ID` and the MC server replays from DB. Zero message loss observed.

5. **Self-loop prevention is essential.** The Bridge must skip messages from its own sender_id to avoid infinite relay loops.

## Risks Validated

| Risk | Assessment |
|------|------------|
| SSE→REST latency for interactive chat | **Low risk** — sub-second total |
| Session mapping vs Gateway semantics | **Compatible** — clean 1:1 mapping |
| SQLite reliability for Bridge state | **Sufficient** — simple, no concurrency issues for single-Bridge deployment |

## What's Next (Foundation Stage)

- Replace canned Gateway with real OpenClaw Gateway integration
- Add API key authentication on the MC SSE stream
- Replace SQLite MC server with PostgreSQL + Redis (production server)
- Add subscription management (filter events by channel membership)
- Handle sub-agent session lifecycle
