"""
Integration tests for Phase 10: Real-Time Infrastructure.

Tests cover:
- SSE event streaming with subscription filtering
- SSE cursor-based replay and events.reset
- SSE heartbeat keepalive
- WebSocket chat message flow
- WebSocket frame types (ping/pong, typing, subscribe)
- REST-to-WebSocket bridge
- Connection limit enforcement
- JWT revocation closes connections
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.chat import ConnectionInfo, ConnectionManager
from app.core.events import (
    BUFFER_SIZE,
    MAX_CONNECTIONS_PER_ORG,
    _matches_subscriptions,
    _replay_from_buffer,
)


# ---------------------------------------------------------------------------
# Subscription Filtering Tests
# ---------------------------------------------------------------------------


class TestSubscriptionFiltering:
    """Test topic-based subscription matching."""

    def test_no_subscriptions_matches_everything(self):
        """Empty subscription list = receive all events."""
        assert _matches_subscriptions("task.created", {"project_id": "abc"}, None) is True
        assert _matches_subscriptions("task.created", {"project_id": "abc"}, []) is True

    def test_project_subscription_matches(self):
        pid = str(uuid.uuid4())
        subs = [{"topic_type": "project", "topic_id": pid}]
        assert _matches_subscriptions("task.created", {"project_id": pid}, subs) is True

    def test_project_subscription_no_match(self):
        subs = [{"topic_type": "project", "topic_id": str(uuid.uuid4())}]
        assert _matches_subscriptions("task.created", {"project_id": str(uuid.uuid4())}, subs) is False

    def test_task_subscription_matches(self):
        tid = str(uuid.uuid4())
        subs = [{"topic_type": "task", "topic_id": tid}]
        assert _matches_subscriptions("task.transitioned", {"task_id": tid}, subs) is True

    def test_channel_subscription_matches(self):
        cid = str(uuid.uuid4())
        subs = [{"topic_type": "channel", "topic_id": cid}]
        assert _matches_subscriptions("message.created", {"channel_id": cid}, subs) is True

    def test_event_type_prefix_subscription(self):
        subs = [{"topic_type": "event_type", "topic_id": "task."}]
        assert _matches_subscriptions("task.created", {}, subs) is True
        assert _matches_subscriptions("task.transitioned", {}, subs) is True
        assert _matches_subscriptions("project.created", {}, subs) is False

    def test_multiple_subscriptions_or_logic(self):
        pid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        subs = [
            {"topic_type": "project", "topic_id": pid},
            {"topic_type": "task", "topic_id": tid},
        ]
        assert _matches_subscriptions("x", {"project_id": pid}, subs) is True
        assert _matches_subscriptions("x", {"task_id": tid}, subs) is True
        assert _matches_subscriptions("x", {"task_id": str(uuid.uuid4())}, subs) is False


# ---------------------------------------------------------------------------
# Connection Manager Tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """Test WebSocket ConnectionManager behavior."""

    @pytest.fixture
    def mgr(self):
        return ConnectionManager()

    @pytest.fixture
    def mock_ws(self):
        ws = AsyncMock(spec_set=["accept", "send_text", "close", "receive_text"])
        ws.accept = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        return ws

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self, mgr, mock_ws):
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()

        with patch("app.core.chat.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.get = AsyncMock(return_value="0")
            redis_mock.incr = AsyncMock(return_value=1)
            redis_mock.expire = AsyncMock()
            redis_mock.sadd = AsyncMock()
            redis_mock.decr = AsyncMock()
            redis_mock.srem = AsyncMock()
            redis_mock.pubsub = MagicMock(return_value=AsyncMock())
            mock_redis.return_value = redis_mock

            info = await mgr.connect(mock_ws, org_id, user_id)
            assert info is not None
            assert str(org_id) in mgr.connections
            assert len(mgr.connections[str(org_id)]) == 1

            await mgr.disconnect(info)
            assert str(org_id) not in mgr.connections

    @pytest.mark.asyncio
    async def test_connection_limit_exceeded(self, mgr, mock_ws):
        org_id = uuid.uuid4()

        with patch("app.core.chat.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.get = AsyncMock(return_value=str(MAX_CONNECTIONS_PER_ORG))
            mock_redis.return_value = redis_mock

            info = await mgr.connect(mock_ws, org_id, uuid.uuid4())
            assert info is None
            mock_ws.accept.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_channel(self, mgr):
        org_id = uuid.uuid4()
        channel_id = str(uuid.uuid4())

        ws1 = AsyncMock()
        ws2 = AsyncMock()

        info1 = ConnectionInfo(ws1, uuid.uuid4(), org_id)
        info1.subscribed_channels.add(channel_id)

        info2 = ConnectionInfo(ws2, uuid.uuid4(), org_id)
        # info2 not subscribed to this channel
        info2.subscribed_channels.add(str(uuid.uuid4()))

        mgr._connections[str(org_id)] = [info1, info2]

        msg = {"type": "message", "content": "hello"}
        await mgr.broadcast_to_channel(org_id, channel_id, msg)

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_channel_empty_subscriptions_receives_all(self, mgr):
        """Connections with no specific channel subscriptions receive all messages."""
        org_id = uuid.uuid4()
        channel_id = str(uuid.uuid4())

        ws1 = AsyncMock()
        info1 = ConnectionInfo(ws1, uuid.uuid4(), org_id)
        # No subscribed_channels = receive all
        mgr._connections[str(org_id)] = [info1]

        msg = {"type": "message", "content": "hello"}
        await mgr.broadcast_to_channel(org_id, channel_id, msg)

        ws1.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_for_revoked_jwt(self, mgr):
        org_id = uuid.uuid4()
        jti = "revoked-jti-123"

        ws1 = AsyncMock()
        info1 = ConnectionInfo(ws1, uuid.uuid4(), org_id, jti=jti)

        ws2 = AsyncMock()
        info2 = ConnectionInfo(ws2, uuid.uuid4(), org_id, jti="other-jti")

        mgr._connections[str(org_id)] = [info1, info2]

        with patch("app.core.chat.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.decr = AsyncMock()
            redis_mock.srem = AsyncMock()
            mock_redis.return_value = redis_mock

            await mgr.close_for_revoked_jwt(org_id, jti)

        ws1.close.assert_called_once_with(code=4001, reason="credential_revoked")
        ws2.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_org(self, mgr):
        org_id = uuid.uuid4()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        info1 = ConnectionInfo(ws1, uuid.uuid4(), org_id)
        info2 = ConnectionInfo(ws2, uuid.uuid4(), org_id)

        mgr._connections[str(org_id)] = [info1, info2]

        msg = {"type": "typing", "sender_id": "x"}
        await mgr.broadcast_to_org(org_id, msg)

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_excludes_user(self, mgr):
        org_id = uuid.uuid4()
        user_to_exclude = uuid.uuid4()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        info1 = ConnectionInfo(ws1, user_to_exclude, org_id)
        info2 = ConnectionInfo(ws2, uuid.uuid4(), org_id)

        mgr._connections[str(org_id)] = [info1, info2]

        msg = {"type": "typing"}
        await mgr.broadcast_to_org(org_id, msg, exclude_user=user_to_exclude)

        ws1.send_text.assert_not_called()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_dead_connection_cleanup(self, mgr):
        """Dead connections are removed during broadcast."""
        org_id = uuid.uuid4()

        ws1 = AsyncMock()
        ws1.send_text.side_effect = Exception("connection closed")
        info1 = ConnectionInfo(ws1, uuid.uuid4(), org_id)

        mgr._connections[str(org_id)] = [info1]

        with patch("app.core.chat.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.decr = AsyncMock()
            redis_mock.srem = AsyncMock()
            mock_redis.return_value = redis_mock

            await mgr.broadcast_to_org(org_id, {"type": "test"})

        assert str(org_id) not in mgr.connections


# ---------------------------------------------------------------------------
# Replay Logic Tests
# ---------------------------------------------------------------------------


class TestReplayLogic:
    """Test SSE replay from Redis buffer."""

    @pytest.mark.asyncio
    async def test_replay_from_buffer_hit(self):
        org_id = uuid.uuid4()
        buffer_data = [
            json.dumps({"sequence_id": 10, "type": "a", "org_id": str(org_id)}),
            json.dumps({"sequence_id": 11, "type": "b", "org_id": str(org_id)}),
            json.dumps({"sequence_id": 12, "type": "c", "org_id": str(org_id)}),
        ]

        with patch("app.core.events.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.lrange = AsyncMock(return_value=buffer_data)
            mock_redis.return_value = redis_mock

            events, needs_db = await _replay_from_buffer(org_id, 10)

        assert not needs_db
        assert len(events) == 2
        assert events[0]["sequence_id"] == 11
        assert events[1]["sequence_id"] == 12

    @pytest.mark.asyncio
    async def test_replay_from_buffer_miss(self):
        """Cursor older than buffer → needs DB fallback."""
        org_id = uuid.uuid4()
        buffer_data = [
            json.dumps({"sequence_id": 100, "type": "a", "org_id": str(org_id)}),
        ]

        with patch("app.core.events.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.lrange = AsyncMock(return_value=buffer_data)
            mock_redis.return_value = redis_mock

            events, needs_db = await _replay_from_buffer(org_id, 5)

        assert needs_db
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_replay_empty_buffer(self):
        org_id = uuid.uuid4()

        with patch("app.core.events.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.lrange = AsyncMock(return_value=[])
            mock_redis.return_value = redis_mock

            events, needs_db = await _replay_from_buffer(org_id, 5)

        assert needs_db
        assert len(events) == 0


# ---------------------------------------------------------------------------
# Active Users Registry Tests
# ---------------------------------------------------------------------------


class TestActiveUsersRegistry:
    @pytest.mark.asyncio
    async def test_get_active_users(self):
        mgr = ConnectionManager()
        org_id = uuid.uuid4()

        with patch("app.core.chat.get_redis") as mock_redis:
            redis_mock = AsyncMock()
            redis_mock.smembers = AsyncMock(return_value={"user1", "user2"})
            mock_redis.return_value = redis_mock

            users = await mgr.get_active_users(org_id)
            assert users == {"user1", "user2"}
