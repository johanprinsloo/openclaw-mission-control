"""
SQLite state persistence for session mappings and event cursors.

Stores:
- session_mappings: channel_id → OpenClaw session_key per agent
- event_cursors: last_sequence_id per agent for SSE resume
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_mappings (
    session_key  TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    org_slug     TEXT NOT NULL,
    channel_id   TEXT NOT NULL,
    channel_type TEXT NOT NULL DEFAULT 'project',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_cursors (
    agent_id         TEXT PRIMARY KEY,
    org_slug         TEXT NOT NULL,
    last_sequence_id TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_channel
    ON session_mappings(channel_id, agent_id);
"""


class BridgeState:
    """Async SQLite state manager for the bridge."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # --- Session Mappings ---

    async def get_session_key(self, channel_id: str, agent_id: str) -> str | None:
        assert self._db
        cursor = await self._db.execute(
            "SELECT session_key FROM session_mappings WHERE channel_id = ? AND agent_id = ?",
            (channel_id, agent_id),
        )
        row = await cursor.fetchone()
        return row["session_key"] if row else None

    async def get_channel_id(self, session_key: str) -> str | None:
        assert self._db
        cursor = await self._db.execute(
            "SELECT channel_id FROM session_mappings WHERE session_key = ?",
            (session_key,),
        )
        row = await cursor.fetchone()
        return row["channel_id"] if row else None

    async def create_session_mapping(
        self,
        session_key: str,
        agent_id: str,
        org_slug: str,
        channel_id: str,
        channel_type: str = "project",
    ) -> None:
        assert self._db
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT OR REPLACE INTO session_mappings
               (session_key, agent_id, org_slug, channel_id, channel_type, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_key, agent_id, org_slug, channel_id, channel_type, now),
        )
        await self._db.commit()

    async def delete_session_mapping(self, session_key: str) -> None:
        assert self._db
        await self._db.execute(
            "DELETE FROM session_mappings WHERE session_key = ?", (session_key,)
        )
        await self._db.commit()

    async def list_sessions(self, agent_id: str) -> list[dict]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT * FROM session_mappings WHERE agent_id = ?", (agent_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # --- Event Cursors ---

    async def get_cursor(self, agent_id: str) -> str | None:
        assert self._db
        cursor = await self._db.execute(
            "SELECT last_sequence_id FROM event_cursors WHERE agent_id = ?",
            (agent_id,),
        )
        row = await cursor.fetchone()
        return row["last_sequence_id"] if row else None

    async def save_cursor(self, agent_id: str, org_slug: str, sequence_id: str) -> None:
        assert self._db
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO event_cursors (agent_id, org_slug, last_sequence_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(agent_id) DO UPDATE SET last_sequence_id=?, updated_at=?""",
            (agent_id, org_slug, sequence_id, now, sequence_id, now),
        )
        await self._db.commit()
