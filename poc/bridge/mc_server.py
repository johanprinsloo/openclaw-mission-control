"""
Minimal Mission Control Server for POC-6: Comms Bridge Round-Trip.

SQLite-backed, no Redis/Postgres required. Provides:
- Channels + Messages REST API
- SSE event stream with sequence_id replay
- command.invoked detection for /slash commands
"""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

DB_PATH = "mc_server.db"

# In-memory subscriber list for SSE push
_subscribers: list[asyncio.Queue] = []


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                org_slug TEXT NOT NULL DEFAULT 'acme',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL REFERENCES channels(id),
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL DEFAULT 'unknown',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_slug TEXT NOT NULL DEFAULT 'acme',
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        # Seed a default channel if none exist
        row = await db.execute("SELECT COUNT(*) FROM channels")
        count = (await row.fetchone())[0]
        if count == 0:
            ch_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO channels (id, name, org_slug, created_at) VALUES (?, ?, ?, ?)",
                (ch_id, "general", "acme", datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
            print(f"[MC] Seeded channel 'general' id={ch_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Mission Control (POC)", lifespan=lifespan)


class PostMessageRequest(BaseModel):
    content: str
    sender_id: str = "user_human"
    sender_name: str = "Human User"


async def _emit_event(db, org_slug: str, event_type: str, payload: dict):
    """Persist event and push to SSE subscribers."""
    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "INSERT INTO events (org_slug, type, payload, created_at) VALUES (?, ?, ?, ?)",
        (org_slug, event_type, json.dumps(payload), now),
    )
    seq_id = cursor.lastrowid
    await db.commit()

    event_data = {
        "sequence_id": seq_id,
        "type": event_type,
        "payload": payload,
        "created_at": now,
    }
    for q in _subscribers:
        await q.put(event_data)
    return seq_id


# --- REST Endpoints ---


@app.get("/api/v1/channels")
async def list_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT * FROM channels")
        return [dict(r) for r in rows]


@app.post("/api/v1/channels/{channel_id}/messages")
async def post_message(channel_id: str, body: PostMessageRequest):
    async with aiosqlite.connect(DB_PATH) as db:
        # Verify channel exists
        row = await db.execute("SELECT id FROM channels WHERE id = ?", (channel_id,))
        if not await row.fetchone():
            raise HTTPException(404, "Channel not found")

        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO messages (id, channel_id, sender_id, sender_name, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, channel_id, body.sender_id, body.sender_name, body.content, now),
        )
        await db.commit()

        payload = {
            "message_id": msg_id,
            "channel_id": channel_id,
            "sender_id": body.sender_id,
            "sender_name": body.sender_name,
            "content": body.content,
        }

        # Detect slash commands
        if body.content.strip().startswith("/"):
            parts = body.content.strip().split(maxsplit=1)
            command = parts[0]
            args = parts[1] if len(parts) > 1 else ""
            cmd_payload = {
                **payload,
                "command": command,
                "args": args,
            }
            await _emit_event(db, "acme", "command.invoked", cmd_payload)
        else:
            await _emit_event(db, "acme", "message.created", payload)

        return {"id": msg_id, "status": "created"}


@app.get("/api/v1/channels/{channel_id}/messages")
async def get_messages(channel_id: str, limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM messages WHERE channel_id = ? ORDER BY created_at DESC LIMIT ?",
            (channel_id, limit),
        )
        return [dict(r) for r in rows]


# --- SSE Stream ---


@app.get("/api/v1/events/stream")
async def event_stream(
    request: Request,
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
):
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)

    async def generate():
        try:
            # Replay missed events
            if last_event_id is not None:
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    rows = await db.execute_fetchall(
                        "SELECT * FROM events WHERE sequence_id > ? ORDER BY sequence_id ASC",
                        (last_event_id,),
                    )
                    for row in rows:
                        evt = dict(row)
                        yield {
                            "event": evt["type"],
                            "id": str(evt["sequence_id"]),
                            "data": json.dumps(
                                {
                                    "sequence_id": evt["sequence_id"],
                                    "type": evt["type"],
                                    "payload": json.loads(evt["payload"]),
                                    "created_at": evt["created_at"],
                                }
                            ),
                        }

            # Live events
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {
                        "event": event_data["type"],
                        "id": str(event_data["sequence_id"]),
                        "data": json.dumps(event_data),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield {"comment": "keepalive"}
        finally:
            _subscribers.remove(queue)

    return EventSourceResponse(generate())


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mission-control-poc"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
