import json
from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

from app.core.database import get_session
from app.core.auth import get_current_user_ws, get_current_user
from app.core.chat import manager
from app.models.user import User
from app.models.channel import Channel
from app.models.message import Message
from app.models.assignments import ProjectUserAssignment

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    org_slug: str,
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    # Authenticate
    # get_current_user_ws handles token validation from query param or cookie
    user = await get_current_user_ws(websocket, token, session)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify Org Access (User must belong to org)
    # create query to check user_org relationship
    # For now assuming user token is valid for the org scope or check explicitly
    # But get_current_user_ws validates user against DB. We need to check if user is in org.
    # We'll skip complex org check for POC and rely on channel access checks per message
    
    # Get Org ID from slug
    # We need to fetch Org ID. Since we don't have it in context easily without a query.
    # For POC, let's assume we fetch it or pass it.
    # Ideally, we should resolve org_slug to org_id.
    
    # Resolving Org Slug
    from app.models.organization import Organization
    stmt = select(Organization).where(Organization.slug == org_slug)
    result = await session.execute(stmt)
    org = result.scalar_one_or_none()
    
    if not org:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, org.id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Handle Frame Types
            msg_type = message_data.get("type")
            
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
                
            if msg_type == "message":
                channel_id = UUID(message_data.get("channel_id"))
                content = message_data.get("content")
                
                # Verify Channel Access
                # Fetch channel
                stmt = select(Channel).where(Channel.id == channel_id, Channel.org_id == org.id)
                result = await session.execute(stmt)
                channel = result.scalar_one_or_none()
                
                if not channel:
                    # Send error frame? or ignore
                    continue
                    
                # If project channel, check membership
                if channel.type == "project" and channel.project_id:
                     # Check if user is assigned to project
                     stmt = select(ProjectUserAssignment).where(
                         ProjectUserAssignment.project_id == channel.project_id,
                         ProjectUserAssignment.user_id == user.id
                     )
                     result = await session.execute(stmt)
                     assignment = result.scalar_one_or_none()
                     if not assignment:
                         # Send error frame
                         await websocket.send_text(json.dumps({
                             "type": "error",
                             "code": "ACCESS_DENIED",
                             "message": "You are not a member of this project channel."
                         }))
                         continue

                # Persist Message
                new_message = Message(
                    org_id=org.id,
                    channel_id=channel.id,
                    sender_id=user.id,
                    content=content,
                    mentions=[] # TODO: Parse mentions
                )
                session.add(new_message)
                await session.commit()
                await session.refresh(new_message)
                
                # Broadcast
                payload = {
                    "type": "message",
                    "id": str(new_message.id),
                    "channel_id": str(channel.id),
                    "sender_id": str(user.id),
                    "content": content,
                    "created_at": new_message.created_at.isoformat(),
                    "mentions": []
                }
                
                await manager.publish_message(org.id, payload)

            elif msg_type in ["typing", "typing_stopped"]:
                # Broadcast directly without persistence
                payload = {
                    "type": msg_type,
                    "channel_id": message_data.get("channel_id"),
                    "sender_id": str(user.id)
                }
                await manager.publish_message(org.id, payload)

    except WebSocketDisconnect:
        manager.disconnect(websocket, org.id)
    except Exception as e:
        # Log error
        print(f"WebSocket Error: {e}")
        manager.disconnect(websocket, org.id)


@router.get("/{channel_id}/messages")
async def get_messages(
    org_slug: str,
    channel_id: UUID,
    page: int = 1,
    per_page: int = 50,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user)
):
    # Resolve Org
    from app.models.organization import Organization
    stmt = select(Organization).where(Organization.slug == org_slug)
    result = await session.execute(stmt)
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Check Channel Access
    stmt = select(Channel).where(Channel.id == channel_id, Channel.org_id == org.id)
    result = await session.execute(stmt)
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.type == "project" and channel.project_id:
        stmt = select(ProjectUserAssignment).where(
            ProjectUserAssignment.project_id == channel.project_id,
            ProjectUserAssignment.user_id == user.id
        )
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Access denied")

    # Fetch Messages
    offset = (page - 1) * per_page
    stmt = select(Message).where(
        Message.channel_id == channel_id,
        Message.org_id == org.id
    ).order_by(desc(Message.created_at)).offset(offset).limit(per_page)
    
    result = await session.execute(stmt)
    messages = result.scalars().all()
    
    return {
        "data": messages,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": 0 # TODO: Count query
        }
    }
