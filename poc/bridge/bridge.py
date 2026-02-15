"""
Comms Bridge for POC-6: SSE listener → Mock Gateway → REST post-back.

Maintains local SQLite state for:
- Session mappings (channel_id → OpenClaw session_key)
- Event cursor (last_sequence_id for SSE reconnection)
"""

import asyncio
import json
import logging
import signal
import sqlite3
import sys
from datetime import datetime, timezone

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BRIDGE] %(message)s")
log = logging.getLogger("bridge")

# Config
MC_BASE_URL = "http://127.0.0.1:8100"
GATEWAY_BASE_URL = "http://127.0.0.1:8200"
AGENT_ID = "agent-builder-01"
ORG_SLUG = "acme"
BRIDGE_DB = "bridge_state.db"
BRIDGE_SENDER_ID = "agent_builder_01"
BRIDGE_SENDER_NAME = "Builder Agent"

# Reconnect settings
RECONNECT_BASE = 1.0
RECONNECT_MAX = 30.0


def init_bridge_db() -> sqlite3.Connection:
    """Initialize the Bridge's local SQLite state."""
    conn = sqlite3.connect(BRIDGE_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_mappings (
            session_key  TEXT PRIMARY KEY,
            agent_id     TEXT NOT NULL,
            org_slug     TEXT NOT NULL,
            channel_id   TEXT NOT NULL,
            channel_type TEXT NOT NULL DEFAULT 'project',
            created_at   TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS event_cursors (
            agent_id       TEXT PRIMARY KEY,
            org_slug       TEXT NOT NULL,
            last_sequence_id INTEGER NOT NULL,
            updated_at     TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def get_last_sequence_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT last_sequence_id FROM event_cursors WHERE agent_id = ?", (AGENT_ID,)
    ).fetchone()
    return row[0] if row else None


def save_sequence_id(conn: sqlite3.Connection, seq_id: int):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO event_cursors (agent_id, org_slug, last_sequence_id, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(agent_id) DO UPDATE SET last_sequence_id=?, updated_at=?""",
        (AGENT_ID, ORG_SLUG, seq_id, now, seq_id, now),
    )
    conn.commit()


def get_or_create_session(conn: sqlite3.Connection, channel_id: str) -> str:
    """Map channel_id to an OpenClaw session key, creating if needed."""
    row = conn.execute(
        "SELECT session_key FROM session_mappings WHERE channel_id = ? AND agent_id = ?",
        (channel_id, AGENT_ID),
    ).fetchone()
    if row:
        return row[0]

    session_key = f"mc:{ORG_SLUG}:project:{channel_id}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO session_mappings (session_key, agent_id, org_slug, channel_id, channel_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_key, AGENT_ID, ORG_SLUG, channel_id, "project", now),
    )
    conn.commit()
    log.info(f"Created session mapping: {channel_id} → {session_key}")
    return session_key


async def handle_message(client: httpx.AsyncClient, conn: sqlite3.Connection, payload: dict):
    """Handle message.created: forward to Gateway, post response back to MC."""
    channel_id = payload["channel_id"]
    content = payload["content"]
    sender = payload.get("sender_name", "unknown")

    # Skip messages from ourselves to avoid loops
    if payload.get("sender_id") == BRIDGE_SENDER_ID:
        return

    session_key = get_or_create_session(conn, channel_id)
    log.info(f"MSG [{channel_id[:8]}] from {sender}: {content}")

    # Forward to Gateway
    resp = await client.post(
        f"{GATEWAY_BASE_URL}/v1/chat",
        json={"session_key": session_key, "message": content, "sender": sender},
    )
    resp.raise_for_status()
    agent_reply = resp.json()["response"]

    # Post back to MC
    resp = await client.post(
        f"{MC_BASE_URL}/api/v1/channels/{channel_id}/messages",
        json={"content": agent_reply, "sender_id": BRIDGE_SENDER_ID, "sender_name": BRIDGE_SENDER_NAME},
    )
    resp.raise_for_status()
    log.info(f"REPLY [{channel_id[:8]}]: {agent_reply}")


async def handle_command(client: httpx.AsyncClient, conn: sqlite3.Connection, payload: dict):
    """Handle command.invoked: forward to Gateway command endpoint, post result back."""
    channel_id = payload["channel_id"]
    command = payload["command"]
    args = payload.get("args", "")

    if payload.get("sender_id") == BRIDGE_SENDER_ID:
        return

    session_key = get_or_create_session(conn, channel_id)
    log.info(f"CMD [{channel_id[:8]}]: {command} {args}")

    resp = await client.post(
        f"{GATEWAY_BASE_URL}/v1/command",
        json={"session_key": session_key, "command": command, "args": args},
    )
    resp.raise_for_status()
    output = resp.json()["output"]

    resp = await client.post(
        f"{MC_BASE_URL}/api/v1/channels/{channel_id}/messages",
        json={"content": output, "sender_id": BRIDGE_SENDER_ID, "sender_name": BRIDGE_SENDER_NAME},
    )
    resp.raise_for_status()
    log.info(f"CMD RESULT [{channel_id[:8]}]: {output[:80]}")


async def sse_listen(conn: sqlite3.Connection):
    """Connect to MC SSE stream and process events. Reconnects on failure."""
    backoff = RECONNECT_BASE

    async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
        while True:
            last_seq = get_last_sequence_id(conn)
            headers = {}
            if last_seq is not None:
                headers["Last-Event-ID"] = str(last_seq)
                log.info(f"Resuming from sequence_id={last_seq}")
            else:
                log.info("Starting fresh (no cursor)")

            url = f"{MC_BASE_URL}/api/v1/events/stream"
            log.info(f"Connecting to SSE: {url}")

            try:
                async with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    log.info("SSE connected")
                    backoff = RECONNECT_BASE  # Reset on successful connect

                    buffer = ""
                    current_event_type = None
                    current_event_id = None
                    current_data_lines = []

                    async for line in response.aiter_lines():
                        line = line.rstrip("\n")

                        if line.startswith("event:"):
                            current_event_type = line[len("event:"):].strip()
                        elif line.startswith("id:"):
                            current_event_id = line[len("id:"):].strip()
                        elif line.startswith("data:"):
                            current_data_lines.append(line[len("data:"):].strip())
                        elif line == "":
                            # End of event
                            if current_data_lines:
                                data_str = "\n".join(current_data_lines)
                                try:
                                    event_data = json.loads(data_str)
                                    event_type = current_event_type or event_data.get("type", "unknown")
                                    payload = event_data.get("payload", event_data)
                                    seq_id = event_data.get("sequence_id")

                                    if event_type == "message.created":
                                        await handle_message(client, conn, payload)
                                    elif event_type == "command.invoked":
                                        await handle_command(client, conn, payload)

                                    if seq_id is not None:
                                        save_sequence_id(conn, seq_id)
                                except json.JSONDecodeError:
                                    log.warning(f"Failed to parse SSE data: {data_str[:100]}")
                                except Exception as e:
                                    log.error(f"Error processing event: {e}")

                            # Reset for next event
                            current_event_type = None
                            current_event_id = None
                            current_data_lines = []
                        elif line.startswith(":"):
                            # Comment (keepalive)
                            pass

            except httpx.HTTPStatusError as e:
                log.error(f"SSE HTTP error: {e.response.status_code}")
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
                log.warning(f"SSE connection lost: {e}")
            except Exception as e:
                log.error(f"SSE unexpected error: {e}")

            log.info(f"Reconnecting in {backoff:.1f}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX)


async def main():
    conn = init_bridge_db()
    log.info("Bridge state DB initialized")
    log.info(f"Agent: {AGENT_ID} | Org: {ORG_SLUG}")

    try:
        await sse_listen(conn)
    except asyncio.CancelledError:
        log.info("Bridge shutting down")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bridge stopped")
