"""
WebSocket Chat and Channel Message endpoints.

- WS /ws — Authenticated WebSocket for real-time chat
- GET /{channel_id}/messages — Paginated message history
- POST /{channel_id}/messages — Post a message (REST, triggers WS broadcast)
"""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import desc, func, text
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

router = APIRouter()


# --- Schemas ---


class PostMessageRequest(BaseModel):
    content: str
    mentions: list[str] = []


class MessageResponse(BaseModel):
    id: str
    channel_id: str
    sender_id: str
    content: str
    mentions: list[str]
    created_at: str


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
    - message → persist + broadcast
    - typing / typing_stopped → broadcast (no persistence)
    - subscribe → subscribe to specific channels

    One connection per org, multiplexing all channels.
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

                # Persist message
                new_message = Message(
                    org_id=auth.org_id,
                    channel_id=channel.id,
                    sender_id=auth.user_id,
                    content=content,
                    mentions=[UUID(m) for m in frame.get("mentions", []) if m],
                )
                session.add(new_message)
                await session.commit()
                await session.refresh(new_message)

                # Build broadcast payload
                payload = {
                    "type": "message",
                    "id": str(new_message.id),
                    "channel_id": str(channel.id),
                    "sender_id": str(auth.user_id),
                    "content": content,
                    "created_at": new_message.created_at.isoformat(),
                    "mentions": [str(m) for m in new_message.mentions] if new_message.mentions else [],
                }

                # Publish to Redis (broadcasts to all processes)
                await manager.publish_message(auth.org_id, payload)
                continue

            # --- Typing Indicators ---
            if frame_type in ("typing", "typing_stopped"):
                channel_id_str = frame.get("channel_id")
                if channel_id_str:
                    payload = {
                        "type": frame_type,
                        "channel_id": channel_id_str,
                        "sender_id": str(auth.user_id),
                    }
                    await manager.publish_message(auth.org_id, payload)
                continue

    except WebSocketDisconnect:
        await manager.disconnect(conn_info)
    except Exception as e:
        logger_msg = f"WebSocket error: {e}"
        import logging
        logging.getLogger(__name__).error(logger_msg)
        await manager.disconnect(conn_info)


# --- REST Message Endpoints ---


@router.get("/{channel_id}/messages")
async def get_messages(
    orgSlug: str,
    channel_id: UUID,
    page: int = 1,
    per_page: int = 50,
    auth: AuthenticatedUser = Depends(require_member),
    session: AsyncSession = Depends(get_session),
):
    """Get paginated message history for a channel."""
    channel = await _get_channel(session, channel_id, auth.org_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not await _verify_channel_access(session, channel, auth.user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Count total
    count_stmt = (
        select(func.count())
        .select_from(Message)
        .where(Message.channel_id == channel_id, Message.org_id == auth.org_id)
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Fetch page
    offset = (page - 1) * per_page
    stmt = (
        select(Message)
        .where(Message.channel_id == channel_id, Message.org_id == auth.org_id)
        .order_by(desc(Message.created_at))
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    messages = result.scalars().all()

    return {
        "data": [
            {
                "id": str(m.id),
                "channel_id": str(m.channel_id),
                "sender_id": str(m.sender_id),
                "content": m.content,
                "mentions": [str(uid) for uid in m.mentions] if m.mentions else [],
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
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

    This is the REST alternative to sending messages via WebSocket.
    The message is persisted and broadcast to all WebSocket clients
    in the channel.
    """
    channel = await _get_channel(session, channel_id, auth.org_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not await _verify_channel_access(session, channel, auth.user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Persist message
    new_message = Message(
        org_id=auth.org_id,
        channel_id=channel.id,
        sender_id=auth.user_id,
        content=body.content,
        mentions=[UUID(m) for m in body.mentions if m],
    )
    session.add(new_message)
    await session.commit()
    await session.refresh(new_message)

    # Build payload for WS broadcast
    ws_payload = {
        "type": "message",
        "id": str(new_message.id),
        "channel_id": str(channel.id),
        "sender_id": str(auth.user_id),
        "content": body.content,
        "created_at": new_message.created_at.isoformat(),
        "mentions": [str(m) for m in new_message.mentions] if new_message.mentions else [],
    }

    # Bridge REST → WebSocket: publish to Redis for WS broadcast
    await manager.publish_message(auth.org_id, ws_payload)

    # Also emit an SSE event for the event stream
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
        actor_type="human" if not hasattr(auth.user, "type") or auth.user.type != "agent" else "agent",
    )

    return {
        "id": str(new_message.id),
        "channel_id": str(channel.id),
        "sender_id": str(auth.user_id),
        "content": body.content,
        "mentions": [str(m) for m in new_message.mentions] if new_message.mentions else [],
        "created_at": new_message.created_at.isoformat(),
    }
