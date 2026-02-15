"""
Production-grade WebSocket chat connection manager.

Features:
- One WS connection per org, multiplexing all channels
- Channel-specific broadcasting (org-wide vs project channels)
- Redis Pub/Sub for multi-process broadcasting
- Connection registry tracking active users/channels per org in Redis
- Connection limit enforcement (shared with SSE: 50 total per org)
- JWT revocation checking
- Graceful cleanup on disconnect
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key prefixes
REDIS_CHAT_CHANNEL_PREFIX = "mc:chat:"
REDIS_WS_CONN_KEY_PREFIX = "mc:ws:connections:"
REDIS_WS_REGISTRY_PREFIX = "mc:ws:registry:"  # Hash: user_id -> connection info
MAX_CONNECTIONS_PER_ORG = 50


class ConnectionInfo:
    """Tracks a single WebSocket connection's metadata."""

    __slots__ = ("websocket", "user_id", "org_id", "subscribed_channels", "jti")

    def __init__(
        self,
        websocket: WebSocket,
        user_id: UUID,
        org_id: UUID,
        jti: str | None = None,
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.org_id = org_id
        self.subscribed_channels: set[str] = set()  # channel_ids this connection listens to
        self.jti = jti


class ConnectionManager:
    """
    Manages WebSocket connections with Redis-backed pub/sub.

    Local connections are tracked in-memory for fast broadcasting.
    Redis pub/sub handles cross-process message distribution.
    Redis registry tracks active users for presence features.
    """

    def __init__(self) -> None:
        # org_id_str -> list[ConnectionInfo]
        self._connections: dict[str, list[ConnectionInfo]] = {}
        # org_id_str -> asyncio.Task (Redis listener)
        self._redis_tasks: dict[str, asyncio.Task] = {}

    @property
    def connections(self) -> dict[str, list[ConnectionInfo]]:
        return self._connections

    async def connect(
        self,
        websocket: WebSocket,
        org_id: UUID,
        user_id: UUID,
        jti: str | None = None,
    ) -> ConnectionInfo | None:
        """
        Accept a WebSocket connection and register it.

        Returns ConnectionInfo on success, None if connection limit exceeded.
        """
        org_str = str(org_id)

        # Check connection limit
        current = await self._get_ws_connection_count(org_id)
        if current >= MAX_CONNECTIONS_PER_ORG:
            return None

        await websocket.accept()

        info = ConnectionInfo(websocket, user_id, org_id, jti)

        if org_str not in self._connections:
            self._connections[org_str] = []
            # Start Redis listener for this org
            self._redis_tasks[org_str] = asyncio.create_task(
                self._listen_redis(org_str)
            )

        self._connections[org_str].append(info)

        # Update Redis registry
        await self._register_connection(org_id, user_id)

        logger.info(
            "WebSocket connected: org=%s user=%s total=%d",
            org_str,
            user_id,
            len(self._connections[org_str]),
        )
        return info

    async def disconnect(self, info: ConnectionInfo) -> None:
        """Remove a connection and clean up."""
        org_str = str(info.org_id)

        if org_str in self._connections:
            try:
                self._connections[org_str].remove(info)
            except ValueError:
                pass

            if not self._connections[org_str]:
                # No more connections for this org
                task = self._redis_tasks.pop(org_str, None)
                if task:
                    task.cancel()
                del self._connections[org_str]

        # Update Redis registry
        await self._unregister_connection(info.org_id, info.user_id)

        logger.info("WebSocket disconnected: org=%s user=%s", org_str, info.user_id)

    async def broadcast_to_channel(
        self,
        org_id: UUID,
        channel_id: str,
        message: dict[str, Any],
        exclude_user: UUID | None = None,
    ) -> None:
        """
        Broadcast a message to all local connections subscribed to a channel.

        For org-wide channels, all connections in the org receive the message.
        For project channels, only connections that have subscribed receive it.
        """
        org_str = str(org_id)
        if org_str not in self._connections:
            return

        msg_text = json.dumps(message) if isinstance(message, dict) else message

        dead_connections = []
        for conn_info in self._connections[org_str]:
            if exclude_user and conn_info.user_id == exclude_user:
                continue

            # Check if connection is subscribed to this channel
            # Empty subscribed_channels means "receive all" (for backwards compat)
            if conn_info.subscribed_channels and channel_id not in conn_info.subscribed_channels:
                continue

            try:
                await conn_info.websocket.send_text(msg_text)
            except Exception:
                dead_connections.append(conn_info)

        # Clean up dead connections
        for dead in dead_connections:
            await self.disconnect(dead)

    async def broadcast_to_org(
        self,
        org_id: UUID,
        message: dict[str, Any],
        exclude_user: UUID | None = None,
    ) -> None:
        """Broadcast to ALL connections in an org (e.g., typing indicators)."""
        org_str = str(org_id)
        if org_str not in self._connections:
            return

        msg_text = json.dumps(message)

        dead_connections = []
        for conn_info in self._connections[org_str]:
            if exclude_user and conn_info.user_id == exclude_user:
                continue
            try:
                await conn_info.websocket.send_text(msg_text)
            except Exception:
                dead_connections.append(conn_info)

        for dead in dead_connections:
            await self.disconnect(dead)

    async def publish_message(self, org_id: UUID, message: dict[str, Any]) -> None:
        """Publish a message to Redis for cross-process broadcasting."""
        redis = await get_redis()
        channel = f"{REDIS_CHAT_CHANNEL_PREFIX}{org_id}"
        await redis.publish(channel, json.dumps(message))

    async def close_for_revoked_jwt(self, org_id: UUID, jti: str) -> None:
        """Close all connections using a revoked JWT."""
        org_str = str(org_id)
        if org_str not in self._connections:
            return

        to_close = [c for c in self._connections[org_str] if c.jti == jti]
        for conn_info in to_close:
            try:
                await conn_info.websocket.close(code=4001, reason="credential_revoked")
            except Exception:
                pass
            await self.disconnect(conn_info)

    async def close_connections_for_user(self, org_id: UUID, user_id: UUID) -> None:
        """Close all connections for a specific user in an org."""
        org_str = str(org_id)
        if org_str not in self._connections:
            return

        to_close = [c for c in self._connections[org_str] if c.user_id == user_id]
        for conn_info in to_close:
            try:
                await conn_info.websocket.close(code=4001, reason="credential_revoked")
            except Exception:
                pass
            await self.disconnect(conn_info)

    # --- Redis Pub/Sub Listener ---

    async def _listen_redis(self, org_id_str: str) -> None:
        """Listen to Redis pub/sub channel for this org and broadcast locally."""
        redis = await get_redis()
        pubsub = redis.pubsub()
        channel = f"{REDIS_CHAT_CHANNEL_PREFIX}{org_id_str}"
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    channel_id = data.get("channel_id")
                    if channel_id:
                        await self.broadcast_to_channel(
                            UUID(org_id_str), channel_id, data
                        )
                    else:
                        await self.broadcast_to_org(UUID(org_id_str), data)
        except asyncio.CancelledError:
            logger.info("Redis WS listener cancelled for org %s", org_id_str)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    # --- Connection Registry (Redis) ---

    async def _get_ws_connection_count(self, org_id: UUID) -> int:
        redis = await get_redis()
        key = f"{REDIS_WS_CONN_KEY_PREFIX}{org_id}"
        val = await redis.get(key)
        return int(val) if val else 0

    async def _register_connection(self, org_id: UUID, user_id: UUID) -> None:
        redis = await get_redis()
        # Increment connection count
        conn_key = f"{REDIS_WS_CONN_KEY_PREFIX}{org_id}"
        await redis.incr(conn_key)
        await redis.expire(conn_key, 3600)

        # Add to user registry (set of active user IDs)
        registry_key = f"{REDIS_WS_REGISTRY_PREFIX}{org_id}"
        await redis.sadd(registry_key, str(user_id))
        await redis.expire(registry_key, 3600)

    async def _unregister_connection(self, org_id: UUID, user_id: UUID) -> None:
        redis = await get_redis()
        conn_key = f"{REDIS_WS_CONN_KEY_PREFIX}{org_id}"
        await redis.decr(conn_key)

        # Check if user still has other connections before removing from registry
        org_str = str(org_id)
        user_still_connected = any(
            c.user_id == user_id
            for c in self._connections.get(org_str, [])
        )
        if not user_still_connected:
            registry_key = f"{REDIS_WS_REGISTRY_PREFIX}{org_id}"
            await redis.srem(registry_key, str(user_id))

    async def get_active_users(self, org_id: UUID) -> set[str]:
        """Get set of user IDs with active WS connections for an org."""
        redis = await get_redis()
        registry_key = f"{REDIS_WS_REGISTRY_PREFIX}{org_id}"
        return await redis.smembers(registry_key)


# Singleton
manager = ConnectionManager()
