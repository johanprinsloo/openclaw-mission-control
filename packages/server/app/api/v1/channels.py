"""
WebSocket Chat and Channel Message endpoints.

- GET / — List channels (org-wide and project)
- GET /{channel_id} — Get channel details
- GET /{channel_id}/messages — Cursor-based paginated message history
- POST /{channel_id}/messages — Post a message (REST, triggers WS broadcast)
- WS /ws — Authenticated WebSocket for real-time chat

Features:
- Mention parsing: extracts @user_id from content, triggers notification events
- Command detection: messages starting with '/' emit 'command.invoked' event
- Cursor-based pagination (newest first)
- REST→WebSocket bridge: REST-posted messages broadcast to WS clients
"""

from __future__ import annotations

import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import desc, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.auth import (
    AuthenticatedUser,
    get_authenticated_user_ws,
    require_member,
)
from app.core.chat import ConnectionManager, manager
from app.core.database import get_session
from app.core.events import broadcast_event
from app.models.assignments import ProjectUserAssignment
from app.models.channel import Channel
from app.models.message import Message
from app.models.user import User
from app.models.user_org import UserOrg

router = APIRouter()
logger = logging.getLogger(__name__)

# Regex for mention parsing: @<uuid> pattern
MENTION_PATTERN = re.compile(r'@([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.IGNORECASE)


# --- Schemas ---


class PostMessageRequest(BaseModel):
    content: str
    mentions: list[str] = []


class MessageResponse(BaseModel):
    id: str
    channel_id: str
    sender_id: str
    sender_display_name: str | None = None
    sender_type: str | None = None
    content: str
    mentions: list[str]
    created_at: str


class ChannelResponse(BaseModel):
    id: str
    name: str
    type: str
    project_id: str | None = None
    created_at: str
    member_count: int = 0
    unread_count: int = 0


# --- Helpers ---


async def _verify_channel_access(
    session: AsyncSession,
    channel: Channel,
    user_id: UUID,
) -> bool:
    """Verify the user has access to a channel. Returns True if allowed."""
    if channel.type == "org_wide":
        return True

    if channel.type == "project" and channel.project_id:
        stmt = select(ProjectUserAssignment).where(
            ProjectUserAssignment.project_id == channel.project_id,
            ProjectUserAssignment.user_id == user_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    return True  # Default allow for unknown channel types


async def _get_channel(
    session: AsyncSession, channel_id: UUID, org_id: UUID
) -> Channel | None:
    stmt = select(Channel).where(Channel.id == channel_id, Channel.org_id == org_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _parse_mentions_from_content(content: str) -> list[UUID]:
    """Extract user UUIDs from @mentions in message content."""
    matches = MENTION_PATTERN.findall(content)
    uuids = []
    for m in matches:
        try:
            uuids.append(UUID(m))
        except ValueError:
            pass
    return uuids


async def _get_sender_info(session: AsyncSession, sender_id: UUID) -> tuple[str | None, str | None]:
    """Get display name and type for a sender."""
    result = await session.execute(select(User).where(User.id == sender_id))
    user = result.scalar_one_or_none()
    if user:
        display_name = user.email or user.identifier or str(user.id)[:8]
        # Try to get display_name from user_org
        return display_name, user.type
    return None, None


async def _enrich_messages(session: AsyncSession, messages: list[Message]) -> list[dict]:
    """Enrich messages with sender display names."""
    # Batch load senders
    sender_ids = list(set(m.sender_id for m in messages))
    sender_map: dict[UUID, tuple[str | None, str | None]] = {}

    if sender_ids:
        result = await session.execute(select(User).where(User.id.in_(sender_ids)))
        users = result.scalars().all()
        for u in users:
            sender_map[u.id] = (u.email or u.identifier or str(u.id)[:8], u.type)

    return [
        {
            "id": str(m.id),
            "channel_id": str(m.channel_id),
            "sender_id": str(m.sender_id),
            "sender_display_name": sender_map.get(m.sender_id, (None,))[0],
            "sender_type": sender_map.get(m.sender_id, (None, None))[1],
            "content": m.content,
            "mentions": [str(uid) for uid in m.mentions] if m.mentions else [],
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


async def _handle_mentions_and_commands(
    session: AsyncSession,
    message: Message,
    auth: AuthenticatedUser,
    channel: Channel,
) -> None:
    """Handle mention notifications and command detection for a message."""
    # Mention notifications
    all_mentions: set[UUID] = set()
    # From explicit mentions field
    if message.mentions:
        all_mentions.update(message.mentions)
    # From content parsing
    parsed = _parse_mentions_from_content(message.content)
    all_mentions.update(parsed)

    for mentioned_user_id in all_mentions:
        if mentioned_user_id != auth.user_id:  # Don't notify self
            await broadcast_event(
                session=session,
                org_id=auth.org_id,
                event_type="mention.created",
                payload={
                    "message_id": str(message.id),
                    "channel_id": str(channel.id),
                    "sender_id": str(auth.user_id),
                    "mentioned_user_id": str(mentioned_user_id),
                },
                actor_id=auth.user_id,
                actor_type=getattr(auth.user, "type", "human"),
            )

    # Command detection
    content_stripped = message.content.strip()
    if content_stripped.startswith("/"):
        parts = content_stripped.split(None, 1)
        command = parts[0][1:]  # Remove leading /
        args = parts[1] if len(parts) > 1 else ""
        await broadcast_event(
            session=session,
            org_id=auth.org_id,
            event_type="command.invoked",
            payload={
                "message_id": str(message.id),
                "channel_id": str(channel.id),
                "sender_id": str(auth.user_id),
                "command": command,
                "args": args,
            },
            actor_id=auth.user_id,
            actor_type=getattr(auth.user, "type", "human"),
        )


# --- Channel List & Details ---


@router.get("")
async def list_channels(
    orgSlug: str,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """List all channels the user has access to."""
    # Get org-wide channels
    org_wide_stmt = select(Channel).where(
        Channel.org_id == auth.org_id,
        Channel.type == "org_wide",
    ).order_by(Channel.name)
    result = await session.execute(org_wide_stmt)
    org_wide_channels = result.scalars().all()

    # Get project channels the user is assigned to
    project_stmt = (
        select(Channel)
        .join(ProjectUserAssignment, and_(
            ProjectUserAssignment.project_id == Channel.project_id,
            ProjectUserAssignment.user_id == auth.user_id,
        ))
        .where(
            Channel.org_id == auth.org_id,
            Channel.type == "project",
        )
        .order_by(Channel.name)
    )
    result = await session.execute(project_stmt)
    project_channels = result.scalars().all()

    all_channels = list(org_wide_channels) + list(project_channels)

    # Get member counts
    channel_data = []
    for ch in all_channels:
        if ch.type == "org_wide":
            # Count all org members
            count_stmt = select(func.count()).select_from(UserOrg).where(UserOrg.org_id == auth.org_id)
        else:
            # Count project members
            count_stmt = select(func.count()).select_from(ProjectUserAssignment).where(
                ProjectUserAssignment.project_id == ch.project_id
            )
        count_result = await session.execute(count_stmt)
        member_count = count_result.scalar() or 0

        channel_data.append({
            "id": str(ch.id),
            "name": ch.name,
            "type": ch.type,
            "project_id": str(ch.project_id) if ch.project_id else None,
            "created_at": ch.created_at.isoformat(),
            "member_count": member_count,
        })

    return {"data": channel_data}


@router.get("/{channel_id}")
async def get_channel_details(
    orgSlug: str,
    channel_id: UUID,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """Get channel details."""
    channel = await _get_channel(session, channel_id, auth.org_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not await _verify_channel_access(session, channel, auth.user_id):
        raise HTTPException(status_code=404, detail="Channel not found")

    # Member count
    if channel.type == "org_wide":
        count_stmt = select(func.count()).select_from(UserOrg).where(UserOrg.org_id == auth.org_id)
    else:
        count_stmt = select(func.count()).select_from(ProjectUserAssignment).where(
            ProjectUserAssignment.project_id == channel.project_id
        )
    count_result = await session.execute(count_stmt)
    member_count = count_result.scalar() or 0

    return {
        "id": str(channel.id),
        "name": channel.name,
        "type": channel.type,
        "project_id": str(channel.project_id) if channel.project_id else None,
        "created_at": channel.created_at.isoformat(),
        "member_count": member_count,
    }


# --- WebSocket Endpoint ---


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    orgSlug: str,
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Authenticated WebSocket endpoint for real-time chat.

    Supports frame types:
    - ping → pong
    - message → persist + broadcast (with mention/command detection)
    - typing / typing_stopped → broadcast (no persistence)
    - subscribe → subscribe to specific channels
    """
    # Authenticate
    try:
        auth = await get_authenticated_user_ws(websocket, orgSlug, token, session)
    except HTTPException:
        await websocket.close(code=4001, reason="authentication_failed")
        return

    # Connect (checks connection limit)
    conn_info = await manager.connect(
        websocket, auth.org_id, auth.user_id, jti=getattr(auth, "_jti", None)
    )
    if conn_info is None:
        await websocket.close(code=4029, reason="connection_limit_exceeded")
        return

    try:
        while True:
            data = await websocket.receive_text()
            try:
                frame = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "INVALID_JSON",
                    "message": "Could not parse message as JSON.",
                }))
                continue

            frame_type = frame.get("type")

            # --- Ping/Pong ---
            if frame_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # --- Subscribe to channels ---
            if frame_type == "subscribe":
                channel_ids = frame.get("channel_ids", [])
                for cid in channel_ids:
                    try:
                        channel = await _get_channel(session, UUID(cid), auth.org_id)
                        if channel and await _verify_channel_access(session, channel, auth.user_id):
                            conn_info.subscribed_channels.add(cid)
                    except (ValueError, Exception):
                        pass
                await websocket.send_text(json.dumps({
                    "type": "subscribed",
                    "channel_ids": list(conn_info.subscribed_channels),
                }))
                continue

            # --- Chat Message ---
            if frame_type == "message":
                channel_id_str = frame.get("channel_id")
                content = frame.get("content")
                client_id = frame.get("client_id")  # For optimistic update dedup

                if not channel_id_str or not content:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "INVALID_MESSAGE",
                        "message": "channel_id and content are required.",
                    }))
                    continue

                try:
                    channel_id = UUID(channel_id_str)
                except ValueError:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "INVALID_CHANNEL_ID",
                        "message": "Invalid channel_id format.",
                    }))
                    continue

                channel = await _get_channel(session, channel_id, auth.org_id)
                if not channel:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "CHANNEL_NOT_FOUND",
                        "message": "Channel not found.",
                    }))
                    continue

                if not await _verify_channel_access(session, channel, auth.user_id):
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "ACCESS_DENIED",
                        "message": "You are not a member of this project channel.",
                    }))
                    continue

                # Parse mentions from content and merge with explicit mentions
                explicit_mentions = [UUID(m) for m in frame.get("mentions", []) if m]
                parsed_mentions = _parse_mentions_from_content(content)
                all_mention_uuids = list(set(explicit_mentions + parsed_mentions))

                # Persist message
                new_message = Message(
                    org_id=auth.org_id,
                    channel_id=channel.id,
                    sender_id=auth.user_id,
                    content=content,
                    mentions=all_mention_uuids,
                )
                session.add(new_message)
                await session.commit()
                await session.refresh(new_message)

                # Get sender info
                display_name, sender_type = await _get_sender_info(session, auth.user_id)

                # Build broadcast payload
                payload = {
                    "type": "message",
                    "id": str(new_message.id),
                    "channel_id": str(channel.id),
                    "sender_id": str(auth.user_id),
                    "sender_display_name": display_name,
                    "sender_type": sender_type,
                    "content": content,
                    "created_at": new_message.created_at.isoformat(),
                    "mentions": [str(m) for m in new_message.mentions] if new_message.mentions else [],
                    "client_id": client_id,  # Echo back for dedup
                }

                # Publish to Redis (broadcasts to all processes)
                await manager.publish_message(auth.org_id, payload)

                # Handle mentions and commands
                await _handle_mentions_and_commands(session, new_message, auth, channel)
                continue

            # --- Typing Indicators ---
            if frame_type in ("typing", "typing_stopped"):
                channel_id_str = frame.get("channel_id")
                if channel_id_str:
                    display_name, _ = await _get_sender_info(session, auth.user_id)
                    payload = {
                        "type": frame_type,
                        "channel_id": channel_id_str,
                        "sender_id": str(auth.user_id),
                        "sender_display_name": display_name,
                    }
                    await manager.publish_message(auth.org_id, payload)
                continue

    except WebSocketDisconnect:
        await manager.disconnect(conn_info)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(conn_info)


# --- REST Message Endpoints ---


@router.get("/{channel_id}/messages")
async def get_messages(
    orgSlug: str,
    channel_id: UUID,
    cursor: Optional[str] = Query(None, description="ISO timestamp cursor for pagination (exclusive, returns older messages)"),
    limit: int = Query(50, ge=1, le=100),
    after: Optional[str] = Query(None, description="ISO timestamp to get messages newer than (for catching up after reconnect)"),
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """
    Get paginated message history for a channel.

    Cursor-based pagination, newest first.
    - No cursor: returns the newest messages.
    - cursor=<ISO timestamp>: returns messages older than the cursor.
    - after=<ISO timestamp>: returns messages newer than the given time (for reconnect catch-up).
    """
    channel = await _get_channel(session, channel_id, auth.org_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not await _verify_channel_access(session, channel, auth.user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Build query
    conditions = [
        Message.channel_id == channel_id,
        Message.org_id == auth.org_id,
    ]

    if after:
        # Catch-up mode: get messages newer than `after`, oldest first
        try:
            after_dt = datetime.fromisoformat(after)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'after' timestamp format")
        conditions.append(Message.created_at > after_dt)
        stmt = (
            select(Message)
            .where(*conditions)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
    else:
        # Normal pagination: newest first
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor format")
            conditions.append(Message.created_at < cursor_dt)

        stmt = (
            select(Message)
            .where(*conditions)
            .order_by(desc(Message.created_at))
            .limit(limit + 1)  # Fetch one extra to detect if there are more
        )

    result = await session.execute(stmt)
    messages = list(result.scalars().all())

    has_more = False
    if not after and len(messages) > limit:
        has_more = True
        messages = messages[:limit]

    enriched = await _enrich_messages(session, messages)

    # Determine next cursor
    next_cursor = None
    if has_more and messages:
        next_cursor = messages[-1].created_at.isoformat()

    return {
        "data": enriched,
        "pagination": {
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        },
    }


@router.post("/{channel_id}/messages", status_code=201)
async def post_message(
    orgSlug: str,
    channel_id: UUID,
    body: PostMessageRequest,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """
    Post a message to a channel via REST.

    The message is persisted and broadcast to all WebSocket clients.
    Mentions are parsed from content and merged with explicit mentions.
    Commands (messages starting with /) emit command.invoked events.
    """
    channel = await _get_channel(session, channel_id, auth.org_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not await _verify_channel_access(session, channel, auth.user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Parse mentions from content and merge with explicit mentions
    explicit_mentions = [UUID(m) for m in body.mentions if m]
    parsed_mentions = _parse_mentions_from_content(body.content)
    all_mention_uuids = list(set(explicit_mentions + parsed_mentions))

    # Persist message
    new_message = Message(
        org_id=auth.org_id,
        channel_id=channel.id,
        sender_id=auth.user_id,
        content=body.content,
        mentions=all_mention_uuids,
    )
    session.add(new_message)
    await session.commit()
    await session.refresh(new_message)

    # Get sender info
    display_name, sender_type = await _get_sender_info(session, auth.user_id)

    # Build payload for WS broadcast
    ws_payload = {
        "type": "message",
        "id": str(new_message.id),
        "channel_id": str(channel.id),
        "sender_id": str(auth.user_id),
        "sender_display_name": display_name,
        "sender_type": sender_type,
        "content": body.content,
        "created_at": new_message.created_at.isoformat(),
        "mentions": [str(m) for m in new_message.mentions] if new_message.mentions else [],
    }

    # Bridge REST → WebSocket
    await manager.publish_message(auth.org_id, ws_payload)

    # SSE event
    await broadcast_event(
        session=session,
        org_id=auth.org_id,
        event_type="message.created",
        payload={
            "message_id": str(new_message.id),
            "channel_id": str(channel.id),
            "sender_id": str(auth.user_id),
        },
        actor_id=auth.user_id,
        actor_type=getattr(auth.user, "type", "human"),
    )

    # Handle mentions and commands
    await _handle_mentions_and_commands(session, new_message, auth, channel)

    return {
        "id": str(new_message.id),
        "channel_id": str(channel.id),
        "sender_id": str(auth.user_id),
        "sender_display_name": display_name,
        "sender_type": sender_type,
        "content": body.content,
        "mentions": [str(m) for m in new_message.mentions] if new_message.mentions else [],
        "created_at": new_message.created_at.isoformat(),
    }
