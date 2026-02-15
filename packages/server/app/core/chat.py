import json
import logging
import asyncio
from typing import Dict, List, Set
from uuid import UUID

from fastapi import WebSocket
from redis.asyncio import Redis

from app.core.events import get_redis

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Map org_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.redis_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, org_id: UUID):
        await websocket.accept()
        org_id_str = str(org_id)
        if org_id_str not in self.active_connections:
            self.active_connections[org_id_str] = set()
            # Start Redis listener for this org if not already running
            self.redis_tasks[org_id_str] = asyncio.create_task(self.listen_redis(org_id_str))
            
        self.active_connections[org_id_str].add(websocket)
        logger.info(f"WebSocket connected: {org_id_str}. Total: {len(self.active_connections[org_id_str])}")

    def disconnect(self, websocket: WebSocket, org_id: UUID):
        org_id_str = str(org_id)
        if org_id_str in self.active_connections:
            self.active_connections[org_id_str].remove(websocket)
            if not self.active_connections[org_id_str]:
                # No more connections for this org, stop Redis listener
                task = self.redis_tasks.pop(org_id_str, None)
                if task:
                    task.cancel()
                del self.active_connections[org_id_str]
        logger.info(f"WebSocket disconnected: {org_id_str}")

    async def broadcast_local(self, org_id: str, message: str):
        """
        Send message to all locally connected clients for this org.
        """
        if org_id in self.active_connections:
            # Copy set to avoid modification during iteration
            for connection in list(self.active_connections[org_id]):
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending message to client: {e}")
                    # Potentially remove dead connection?
                    # disconnect() handles removal logic but better to let connection handler do it.

    async def publish_message(self, org_id: UUID, message: dict):
        """
        Publish message to Redis channel for this org.
        """
        redis = await get_redis()
        channel = f"mc:chat:{str(org_id)}"
        await redis.publish(channel, json.dumps(message))

    async def listen_redis(self, org_id: str):
        """
        Listen to Redis channel for this org and broadcast to local clients.
        """
        redis = await get_redis()
        pubsub = redis.pubsub()
        channel = f"mc:chat:{org_id}"
        await pubsub.subscribe(channel)
        
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    await self.broadcast_local(org_id, message['data'])
        except asyncio.CancelledError:
            logger.info(f"Redis listener cancelled for {org_id}")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

manager = ConnectionManager()
