import json
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import asyncio

from redis.asyncio import Redis
from fastapi import Request
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.database import get_session
from app.models.event import Event

# Redis Config
REDIS_URL = "redis://localhost:6379/0"
REDIS_PUBSUB_CHANNEL = "mc:events:pubsub"
REDIS_BUFFER_KEY_PREFIX = "mc:sse:buffer:"
BUFFER_SIZE = 100

logger = logging.getLogger(__name__)

# Singleton Redis client
_redis: Optional[Redis] = None

async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis

async def broadcast_event(
    session,
    org_id: UUID,
    event_type: str,
    payload: Dict[str, Any],
    actor_id: Optional[UUID] = None,
    actor_type: str = "system",
):
    """
    1. Persist to DB (using provided session)
    2. Add to Redis buffer
    3. Publish to Redis Pub/Sub
    """
    
    # 1. Persist to DB
    new_event = Event(
        org_id=org_id,
        type=event_type,
        actor_id=actor_id,
        actor_type=actor_type,
        payload=payload,
        timestamp=datetime.utcnow()
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
        "timestamp": new_event.timestamp.isoformat()
    }
    
    redis = await get_redis()
    
    # 2. Add to Redis Buffer (Circular)
    buffer_key = f"{REDIS_BUFFER_KEY_PREFIX}{str(org_id)}"
    event_json = json.dumps(event_data)
    
    async with redis.pipeline() as pipe:
        # LPUSH adds to the head (left). So index 0 is newest.
        pipe.lpush(buffer_key, event_json)
        pipe.ltrim(buffer_key, 0, BUFFER_SIZE - 1)
        pipe.expire(buffer_key, 60 * 60 * 24) # 24h
        await pipe.execute()
        
    # 3. Publish to Redis Pub/Sub
    await redis.publish(REDIS_PUBSUB_CHANNEL, event_json)
    
    return new_event


async def event_generator(
    request: Request,
    org_id: UUID,
    last_event_id: Optional[int] = None
):
    """
    SSE Generator.
    Yields event data as strings formatted for SSE.
    """
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_PUBSUB_CHANNEL)
    
    max_seen_id = last_event_id or -1
    replayed_events = []

    # --- Replay Phase ---
    if last_event_id is not None:
        buffer_key = f"{REDIS_BUFFER_KEY_PREFIX}{str(org_id)}"
        # Redis List is LIFO (head is newest).
        buffered_events_raw = await redis.lrange(buffer_key, 0, -1)
        
        # Parse and Sort by sequence_id ASC (oldest first)
        buffered_events = [json.loads(e) for e in buffered_events_raw]
        buffered_events.sort(key=lambda x: x['sequence_id'])
        
        # Determine range in buffer
        min_buf_id = buffered_events[0]['sequence_id'] if buffered_events else None
        
        if min_buf_id is not None and last_event_id >= min_buf_id:
             replayed_events = [e for e in buffered_events if e['sequence_id'] > last_event_id]
        else:
            async for session in get_session():
                stmt = select(Event).where(
                    Event.org_id == org_id,
                    Event.sequence_id > last_event_id
                ).order_by(Event.sequence_id).limit(1000)
                result = await session.execute(stmt)
                db_events = result.scalars().all()
                
                for event in db_events:
                    replayed_events.append({
                        "id": str(event.id),
                        "sequence_id": event.sequence_id,
                        "org_id": str(event.org_id),
                        "type": event.type,
                        "actor_id": str(event.actor_id) if event.actor_id else None,
                        "actor_type": event.actor_type,
                        "payload": event.payload,
                        "timestamp": event.timestamp.isoformat()
                    })
                break
    
    # Yield replayed events
    for event_data in replayed_events:
        if event_data['sequence_id'] > max_seen_id:
            max_seen_id = event_data['sequence_id']
            yield {
                "event": event_data['type'],
                "id": event_data['sequence_id'],
                "data": json.dumps(event_data)
            }
                
    # --- Live Phase ---
    try:
        async for message in pubsub.listen():
            if await request.is_disconnected():
                break
                
            if message['type'] == 'message':
                event_data = json.loads(message['data'])
                if str(event_data['org_id']) == str(org_id):
                    if event_data['sequence_id'] > max_seen_id:
                        max_seen_id = event_data['sequence_id']
                        yield {
                            "event": event_data['type'],
                            "id": event_data['sequence_id'],
                            "data": json.dumps(event_data)
                        }
    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for org {org_id}")
    finally:
        await pubsub.unsubscribe(REDIS_PUBSUB_CHANNEL)
        await pubsub.close()
