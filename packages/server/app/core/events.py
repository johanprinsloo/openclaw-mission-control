"""
Production-grade SSE event streaming with Redis Pub/Sub.

Features:
- Topic-based subscription filtering
- Cursor-based replay from Redis buffer or database fallback
- events.reset when cursor is older than retention
- Keepalive heartbeat every 30 seconds
- JWT revocation checking during streaming
- Connection limit enforcement per org
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_session
from app.core.redis import get_redis
from app.models.event import Event

logger = logging.getLogger(__name__)

# Configuration
REDIS_PUBSUB_CHANNEL = "mc:events:pubsub"
REDIS_BUFFER_KEY_PREFIX = "mc:sse:buffer:"
REDIS_SSE_CONN_KEY_PREFIX = "mc:sse:connections:"
BUFFER_SIZE = 500
HEARTBEAT_INTERVAL = 30  # seconds
MAX_CONNECTIONS_PER_ORG = 50
MAX_REPLAY_EVENTS = 1000


async def broadcast_event(
    session: AsyncSession,
    org_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    actor_id: UUID | None = None,
    actor_type: str = "system",
) -> Event:
    """
    Persist event to DB, buffer in Redis, and publish to Pub/Sub.

    This is the single entry point for all event broadcasting.
    REST endpoints and internal services call this to emit events
    that will be delivered to SSE clients.
    """
    # 1. Persist to DB
    new_event = Event(
        org_id=org_id,
        type=event_type,
        actor_id=actor_id,
        actor_type=actor_type,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
    )
    session.add(new_event)
    await session.commit()
    await session.refresh(new_event)

    event_data = {
        "id": str(new_event.id),
        "sequence_id": new_event.sequence_id,
        "org_id": str(org_id),
        "type": event_type,
        "actor_id": str(actor_id) if actor_id else None,
        "actor_type": actor_type,
        "payload": payload,
        "timestamp": new_event.timestamp.isoformat(),
    }

    redis = await get_redis()

    # 2. Buffer in Redis (circular list)
    buffer_key = f"{REDIS_BUFFER_KEY_PREFIX}{org_id}"
    event_json = json.dumps(event_data)

    async with redis.pipeline() as pipe:
        pipe.lpush(buffer_key, event_json)
        pipe.ltrim(buffer_key, 0, BUFFER_SIZE - 1)
        pipe.expire(buffer_key, 86400)  # 24h retention
        await pipe.execute()

    # 3. Publish to Redis Pub/Sub
    await redis.publish(REDIS_PUBSUB_CHANNEL, event_json)

    return new_event


async def _increment_sse_connections(org_id: UUID) -> int:
    """Increment SSE connection counter for an org. Returns new count."""
    redis = await get_redis()
    key = f"{REDIS_SSE_CONN_KEY_PREFIX}{org_id}"
    count = await redis.incr(key)
    await redis.expire(key, 3600)  # auto-expire safety net
    return count


async def _decrement_sse_connections(org_id: UUID) -> None:
    """Decrement SSE connection counter for an org."""
    redis = await get_redis()
    key = f"{REDIS_SSE_CONN_KEY_PREFIX}{org_id}"
    await redis.decr(key)


async def get_sse_connection_count(org_id: UUID) -> int:
    """Get current SSE connection count for an org."""
    redis = await get_redis()
    key = f"{REDIS_SSE_CONN_KEY_PREFIX}{org_id}"
    val = await redis.get(key)
    return int(val) if val else 0


async def _check_jwt_revoked(jti: str | None) -> bool:
    """Check if the JWT has been revoked."""
    if not jti:
        return False
    redis = await get_redis()
    return await redis.exists(f"jwt:revoked:{jti}") > 0


def _matches_subscriptions(
    event_type: str,
    event_payload: dict,
    subscriptions: list[dict] | None,
) -> bool:
    """
    Check if an event matches the user's subscription filters.

    If subscriptions is None or empty, all events pass (no filter).
    Subscriptions are topic-based: {topic_type: "project", topic_id: "..."}
    Events match if their payload references a subscribed topic.
    """
    if not subscriptions:
        return True  # No filter = receive everything

    # Extract topic references from event
    payload_project_id = event_payload.get("project_id")
    payload_task_id = event_payload.get("task_id")
    payload_channel_id = event_payload.get("channel_id")

    for sub in subscriptions:
        topic_type = sub.get("topic_type")
        topic_id = sub.get("topic_id")

        if topic_type == "project" and payload_project_id and str(payload_project_id) == str(topic_id):
            return True
        if topic_type == "task" and payload_task_id and str(payload_task_id) == str(topic_id):
            return True
        if topic_type == "channel" and payload_channel_id and str(payload_channel_id) == str(topic_id):
            return True

        # Match by event type prefix (e.g., subscribe to "task.*" events)
        if topic_type == "event_type" and event_type.startswith(str(topic_id)):
            return True

    return False


async def _replay_from_buffer(
    org_id: UUID, last_event_id: int
) -> tuple[list[dict], bool]:
    """
    Try to replay events from Redis buffer.

    Returns (events, needs_db_fallback).
    If last_event_id is older than buffer contents, needs_db_fallback=True.
    """
    redis = await get_redis()
    buffer_key = f"{REDIS_BUFFER_KEY_PREFIX}{org_id}"
    raw_events = await redis.lrange(buffer_key, 0, -1)

    if not raw_events:
        return [], True  # Empty buffer, fall back to DB

    buffered = [json.loads(e) for e in raw_events]
    buffered.sort(key=lambda x: x["sequence_id"])

    min_buf_id = buffered[0]["sequence_id"]

    if last_event_id >= min_buf_id:
        # Buffer covers this range
        return [e for e in buffered if e["sequence_id"] > last_event_id], False
    else:
        # Buffer doesn't go back far enough
        return [], True


async def _replay_from_db(
    org_id: UUID, last_event_id: int
) -> tuple[list[dict], bool]:
    """
    Replay events from database.

    Returns (events, should_reset).
    If no events found and last_event_id > 0, the cursor is too old → reset.
    """
    events = []
    async for session in get_session():
        # Check if the requested sequence_id still exists
        stmt = (
            select(func.min(Event.sequence_id))
            .where(Event.org_id == org_id)
        )
        result = await session.execute(stmt)
        min_seq = result.scalar()

        if min_seq is not None and last_event_id < min_seq - 1:
            # Cursor is older than retention — need reset
            return [], True

        stmt = (
            select(Event)
            .where(Event.org_id == org_id, Event.sequence_id > last_event_id)
            .order_by(Event.sequence_id)
            .limit(MAX_REPLAY_EVENTS)
        )
        result = await session.execute(stmt)
        db_events = result.scalars().all()

        for event in db_events:
            events.append({
                "id": str(event.id),
                "sequence_id": event.sequence_id,
                "org_id": str(event.org_id),
                "type": event.type,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "actor_type": event.actor_type,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            })
        break

    return events, False


async def event_generator(
    request: Request,
    org_id: UUID,
    last_event_id: int | None = None,
    subscriptions: list[dict] | None = None,
    jti: str | None = None,
) -> AsyncGenerator[dict | str, None]:
    """
    Production SSE generator with:
    - Cursor-based replay (buffer → DB fallback → events.reset)
    - Topic-based subscription filtering
    - 30s keepalive heartbeat
    - JWT revocation checking
    - Graceful cleanup on disconnect
    """
    # Track connection
    count = await _increment_sse_connections(org_id)
    if count > MAX_CONNECTIONS_PER_ORG:
        await _decrement_sse_connections(org_id)
        yield {
            "event": "error",
            "data": json.dumps({"code": "CONNECTION_LIMIT", "message": "Too many connections"}),
        }
        return

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_PUBSUB_CHANNEL)

    max_seen_id = last_event_id or -1

    try:
        # --- Replay Phase ---
        if last_event_id is not None and last_event_id >= 0:
            replay_events, needs_db = await _replay_from_buffer(org_id, last_event_id)

            if needs_db:
                replay_events, should_reset = await _replay_from_db(org_id, last_event_id)
                if should_reset:
                    yield {
                        "event": "events.reset",
                        "data": json.dumps({
                            "reason": "cursor_expired",
                            "message": "Requested sequence ID is older than retention. Full refresh required.",
                        }),
                    }
                    # Continue streaming live events from here

            for event_data in replay_events:
                if event_data["sequence_id"] > max_seen_id:
                    if _matches_subscriptions(
                        event_data["type"], event_data.get("payload", {}), subscriptions
                    ):
                        max_seen_id = event_data["sequence_id"]
                        yield {
                            "event": event_data["type"],
                            "id": str(event_data["sequence_id"]),
                            "data": json.dumps(event_data),
                        }

        # --- Live Phase ---
        revocation_check_counter = 0
        while True:
            if await request.is_disconnected():
                break

            # Check JWT revocation periodically (every 10 iterations ≈ every 10s)
            revocation_check_counter += 1
            if revocation_check_counter >= 10 and jti:
                revocation_check_counter = 0
                if await _check_jwt_revoked(jti):
                    yield {
                        "event": "session.revoked",
                        "data": json.dumps({"reason": "credential_revoked"}),
                    }
                    break

            # Non-blocking poll with timeout for heartbeat
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                message = None

            if message is None:
                # Heartbeat
                yield ": heartbeat\n\n"
                continue

            if message["type"] == "message":
                event_data = json.loads(message["data"])
                if str(event_data["org_id"]) == str(org_id):
                    if event_data["sequence_id"] > max_seen_id:
                        if _matches_subscriptions(
                            event_data["type"],
                            event_data.get("payload", {}),
                            subscriptions,
                        ):
                            max_seen_id = event_data["sequence_id"]
                            yield {
                                "event": event_data["type"],
                                "id": str(event_data["sequence_id"]),
                                "data": json.dumps(event_data),
                            }

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for org %s", org_id)
    finally:
        await _decrement_sse_connections(org_id)
        await pubsub.unsubscribe(REDIS_PUBSUB_CHANNEL)
        await pubsub.close()
