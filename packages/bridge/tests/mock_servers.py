"""
Mock Mission Control and Gateway servers for integration testing.

MC Server: channels, messages, SSE stream with sequence_id replay.
Gateway: canned chat and command responses.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# ── Mock Mission Control ──

MC_DB = ":memory:"


class _MCState:
    def __init__(self):
        self.db: aiosqlite.Connection | None = None
        self.subscribers: list[asyncio.Queue] = []


async def init_mc_db(db: aiosqlite.Connection):
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS channels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            org_slug TEXT NOT NULL DEFAULT 'test-org',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL DEFAULT 'unknown',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_slug TEXT NOT NULL DEFAULT 'test-org',
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    # Seed channel
    ch_id = "ch_test_001"
    await db.execute(
        "INSERT OR IGNORE INTO channels (id, name, org_slug, created_at) VALUES (?, ?, ?, ?)",
        (ch_id, "general", "test-org", datetime.now(timezone.utc).isoformat()),
    )
    await db.commit()


def create_mc_app(db_path: str = ":memory:") -> FastAPI:
    """Create a mock MC FastAPI app using the given SQLite DB."""
    app = FastAPI(title="Mock MC")

    class PostMsg(BaseModel):
        content: str
        sender_id: str = "user_human"
        sender_name: str = "Human User"

    mc = _MCState()

    @app.on_event("startup")
    async def startup():
        mc.db = await aiosqlite.connect(db_path)
        mc.db.row_factory = aiosqlite.Row
        await init_mc_db(mc.db)

    @app.on_event("shutdown")
    async def shutdown():
        if mc.db:
            await mc.db.close()

    async def emit_event(org_slug: str, event_type: str, payload: dict):
        assert mc.db
        now = datetime.now(timezone.utc).isoformat()
        cursor = await mc.db.execute(
            "INSERT INTO events (org_slug, type, payload, created_at) VALUES (?, ?, ?, ?)",
            (org_slug, event_type, json.dumps(payload), now),
        )
        seq_id = cursor.lastrowid
        await mc.db.commit()
        event_data = {"sequence_id": seq_id, "type": event_type, "payload": payload, "created_at": now}
        for q in mc.subscribers:
            await q.put(event_data)
        return seq_id

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/channels")
    async def list_channels():
        assert mc.db
        rows = await mc.db.execute_fetchall("SELECT * FROM channels")
        return [dict(r) for r in rows]

    @app.post("/api/v1/channels/{channel_id}/messages")
    async def post_message(channel_id: str, body: PostMsg):
        assert mc.db
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await mc.db.execute(
            "INSERT INTO messages (id, channel_id, sender_id, sender_name, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, channel_id, body.sender_id, body.sender_name, body.content, now),
        )
        await mc.db.commit()

        payload = {
            "message_id": msg_id,
            "channel_id": channel_id,
            "sender_id": body.sender_id,
            "sender_name": body.sender_name,
            "content": body.content,
        }

        if body.content.strip().startswith("/"):
            parts = body.content.strip().split(maxsplit=1)
            cmd_payload = {**payload, "command": parts[0], "args": parts[1] if len(parts) > 1 else ""}
            await emit_event("test-org", "command.invoked", cmd_payload)
        else:
            await emit_event("test-org", "message.created", payload)

        return {"id": msg_id, "status": "created"}

    @app.get("/api/v1/channels/{channel_id}/messages")
    async def get_messages(channel_id: str, limit: int = 50):
        assert mc.db
        rows = await mc.db.execute_fetchall(
            "SELECT * FROM messages WHERE channel_id = ? ORDER BY created_at DESC LIMIT ?",
            (channel_id, limit),
        )
        return [dict(r) for r in rows]

    @app.get("/api/v1/orgs/{org_slug}/events/stream")
    async def event_stream(
        request: Request,
        org_slug: str,
        last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    ):
        queue: asyncio.Queue = asyncio.Queue()
        mc.subscribers.append(queue)

        async def generate():
            try:
                if last_event_id is not None and mc.db:
                    rows = await mc.db.execute_fetchall(
                        "SELECT * FROM events WHERE sequence_id > ? ORDER BY sequence_id ASC",
                        (last_event_id,),
                    )
                    for row in rows:
                        evt = dict(row)
                        yield {
                            "event": evt["type"],
                            "id": str(evt["sequence_id"]),
                            "data": json.dumps({
                                "sequence_id": evt["sequence_id"],
                                "type": evt["type"],
                                "payload": json.loads(evt["payload"]),
                                "created_at": evt["created_at"],
                            }),
                        }
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
                        yield {"comment": "keepalive"}
            finally:
                mc.subscribers.remove(queue)

        return EventSourceResponse(generate())

    return app


# ── Mock Gateway ──

def create_gateway_app() -> FastAPI:
    app = FastAPI(title="Mock Gateway")

    class ChatReq(BaseModel):
        session_key: str
        message: str
        sender: str = "unknown"

    class CmdReq(BaseModel):
        session_key: str
        command: str
        args: str = ""

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/chat")
    async def chat(req: ChatReq):
        return {"session_key": req.session_key, "response": f"Agent response to: {req.message}"}

    @app.post("/v1/command")
    async def command(req: CmdReq):
        if req.command == "/status":
            output = f"🟢 Status for session {req.session_key}:\n  Active tasks: 3\n  Pending reviews: 1"
        else:
            output = f"Unknown command: {req.command}"
        return {"session_key": req.session_key, "output": output}

    return app
