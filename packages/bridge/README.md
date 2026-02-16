# OpenClaw ↔ Mission Control Comms Bridge

The Comms Bridge connects OpenClaw agents to Mission Control channels, relaying messages, commands, and events between the two systems.

## Architecture

```
OpenClaw Gateway  ◄──►  Comms Bridge  ◄──SSE/REST──►  Mission Control
```

Agents never connect to Mission Control directly. The Bridge is the single integration point — translating MC events into Gateway session messages and posting agent responses back to MC channels.

## Quick Start

```bash
# Install
pip install -e ".[test]"

# Configure
cp comms-bridge.example.yaml comms-bridge.yaml
# Edit comms-bridge.yaml with your MC URL, agent API keys, etc.

# Set secrets (API keys loaded from env vars, never from config)
export MC_API_KEY_BUILDER_01="mc_ak_live_..."
export OPENCLAW_GATEWAY_KEY="gw_..."

# Run
mc-bridge -c comms-bridge.yaml
```

## Modules

| Module | Responsibility |
|--------|---------------|
| `config.py` | YAML config loading + Pydantic validation |
| `state.py` | SQLite persistence (session mappings, event cursors) |
| `sse_listener.py` | Persistent SSE connection with reconnection + backoff |
| `relay.py` | Message translation between MC REST and Gateway |
| `router.py` | Event dispatch, command routing, self-loop prevention |
| `subscriptions.py` | Topic subscription management |
| `metrics.py` | Prometheus-compatible metrics collection |
| `health.py` | HTTP health + metrics endpoints |
| `bridge.py` | Main orchestrator: lifecycle, signal handling |
| `main.py` | CLI entry point |

## Bridge Commands

Send these in any MC channel:

- `mc-bridge subscribe {topic}` — Subscribe to a topic
- `mc-bridge unsubscribe {topic}` — Unsubscribe from a topic
- `mc-bridge subscriptions` — List active subscriptions

## Health & Metrics

- `GET http://localhost:9090/health` — JSON health status
- `GET http://localhost:9090/metrics` — Prometheus metrics

## Testing

```bash
pytest tests/ -v
```

## Session Mapping

| MC Entity | Session Key Format |
|-----------|-------------------|
| Project channel | `mc:{orgSlug}:project:{channelId}` |
| Org-wide channel | `mc:{orgSlug}:org:{channelId}` |
| Sub-agent task | `mc:{orgSlug}:sub:{subAgentId}` |
