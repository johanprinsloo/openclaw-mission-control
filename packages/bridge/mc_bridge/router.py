"""
Command and message routing logic.

Routes incoming SSE events to the appropriate handler based on event type.
Manages session resolution and self-loop prevention.
"""

from __future__ import annotations

from typing import Any

import structlog

from .config import AgentConfig
from .relay import MessageRelay
from .sse_listener import SSEEvent
from .state import BridgeState
from .subscriptions import SubscriptionManager

log = structlog.get_logger()


class EventRouter:
    """
    Routes SSE events to the correct handler.

    Responsibilities:
    - Resolve session keys for channels
    - Prevent self-loops (skip own messages)
    - Dispatch message.created → relay to Gateway → post response
    - Dispatch command.invoked → relay to Gateway → post output
    - Handle subscription management commands (mc-bridge subscribe)
    """

    def __init__(
        self,
        agent: AgentConfig,
        state: BridgeState,
        relay: MessageRelay,
        subscriptions: SubscriptionManager,
    ):
        self._agent = agent
        self._state = state
        self._relay = relay
        self._subscriptions = subscriptions
        self._sender_id = agent.name.replace("-", "_")
        self._sender_name = agent.name

    async def handle_event(self, event: SSEEvent) -> None:
        """Main event dispatch."""
        payload = event.data

        if event.event_type == "message.created":
            await self._handle_message(payload)
        elif event.event_type == "command.invoked":
            await self._handle_command(payload)
        elif event.event_type == "project.user_assigned":
            await self._handle_assignment(payload)
        elif event.event_type == "project.user_unassigned":
            await self._handle_unassignment(payload)
        elif event.event_type == "sub_agent.created":
            await self._handle_sub_agent_created(payload)
        elif event.event_type == "sub_agent.terminated":
            await self._handle_sub_agent_terminated(payload)

        # Persist cursor
        if event.sequence_id:
            await self._state.save_cursor(
                self._agent.name, self._agent.org_slug, event.sequence_id
            )

    async def _handle_message(self, payload: dict[str, Any]) -> None:
        # Self-loop prevention
        if payload.get("sender_id") == self._sender_id:
            return

        channel_id = payload.get("channel_id", "")
        content = payload.get("content", "")
        sender = payload.get("sender_name", "unknown")

        # Check for bridge management commands
        if content.strip().startswith("mc-bridge "):
            await self._handle_bridge_command(channel_id, content.strip())
            return

        session_key = await self._resolve_session(channel_id)
        log.info(
            "router.message",
            channel=channel_id[:8],
            sender=sender,
            session=session_key,
        )

        response = await self._relay.forward_to_gateway(session_key, content, sender)
        if response:
            await self._relay.post_to_mc(
                channel_id,
                response,
                self._sender_id,
                self._sender_name,
                self._agent.api_key or "",
                self._agent.org_slug,
            )

    async def _handle_command(self, payload: dict[str, Any]) -> None:
        if payload.get("sender_id") == self._sender_id:
            return

        channel_id = payload.get("channel_id", "")
        command = payload.get("command", "")
        args = payload.get("args", "")

        session_key = await self._resolve_session(channel_id)
        log.info(
            "router.command",
            channel=channel_id[:8],
            command=command,
            session=session_key,
        )

        output = await self._relay.forward_command_to_gateway(
            session_key, command, args
        )
        if output:
            await self._relay.post_to_mc(
                channel_id,
                output,
                self._sender_id,
                self._sender_name,
                self._agent.api_key or "",
                self._agent.org_slug,
            )

    async def _handle_bridge_command(self, channel_id: str, text: str) -> None:
        """Handle mc-bridge commands (e.g., mc-bridge subscribe {topic})."""
        parts = text.split()
        if len(parts) < 2:
            return

        subcmd = parts[1]
        if subcmd == "subscribe" and len(parts) >= 3:
            topic = parts[2]
            self._subscriptions.subscribe(topic)
            await self._relay.post_to_mc(
                channel_id,
                f"✅ Subscribed to topic: {topic}",
                self._sender_id,
                self._sender_name,
                self._agent.api_key or "",
                self._agent.org_slug,
            )
            log.info("router.subscribe", topic=topic)
        elif subcmd == "unsubscribe" and len(parts) >= 3:
            topic = parts[2]
            self._subscriptions.unsubscribe(topic)
            await self._relay.post_to_mc(
                channel_id,
                f"✅ Unsubscribed from topic: {topic}",
                self._sender_id,
                self._sender_name,
                self._agent.api_key or "",
                self._agent.org_slug,
            )
            log.info("router.unsubscribe", topic=topic)
        elif subcmd == "subscriptions":
            topics = self._subscriptions.list_topics()
            msg = "📋 Active subscriptions:\n" + "\n".join(f"  • {t}" for t in topics) if topics else "No active subscriptions."
            await self._relay.post_to_mc(
                channel_id,
                msg,
                self._sender_id,
                self._sender_name,
                self._agent.api_key or "",
                self._agent.org_slug,
            )

    async def _handle_assignment(self, payload: dict[str, Any]) -> None:
        """Handle project.user_assigned: create session mapping."""
        user_id = payload.get("user_id", "")
        if user_id != self._agent.name:
            return
        project_id = payload.get("project_id", "")
        channel_id = payload.get("channel_id", "")
        if channel_id:
            session_key = f"mc:{self._agent.org_slug}:project:{project_id}"
            await self._state.create_session_mapping(
                session_key, self._agent.name, self._agent.org_slug,
                channel_id, "project",
            )
            log.info("router.assignment", project=project_id, channel=channel_id)

    async def _handle_unassignment(self, payload: dict[str, Any]) -> None:
        """Handle project.user_unassigned: remove session mapping."""
        user_id = payload.get("user_id", "")
        if user_id != self._agent.name:
            return
        project_id = payload.get("project_id", "")
        session_key = f"mc:{self._agent.org_slug}:project:{project_id}"
        await self._state.delete_session_mapping(session_key)
        log.info("router.unassignment", project=project_id)

    async def _handle_sub_agent_created(self, payload: dict[str, Any]) -> None:
        sub_agent_id = payload.get("sub_agent_id", "")
        channel_id = payload.get("channel_id", "")
        if sub_agent_id and channel_id:
            session_key = f"mc:{self._agent.org_slug}:sub:{sub_agent_id}"
            await self._state.create_session_mapping(
                session_key, self._agent.name, self._agent.org_slug,
                channel_id, "sub_agent",
            )
            log.info("router.sub_agent_created", sub_agent=sub_agent_id)

    async def _handle_sub_agent_terminated(self, payload: dict[str, Any]) -> None:
        sub_agent_id = payload.get("sub_agent_id", "")
        if sub_agent_id:
            session_key = f"mc:{self._agent.org_slug}:sub:{sub_agent_id}"
            await self._state.delete_session_mapping(session_key)
            log.info("router.sub_agent_terminated", sub_agent=sub_agent_id)

    async def _resolve_session(self, channel_id: str) -> str:
        """Get or create session key for a channel."""
        existing = await self._state.get_session_key(channel_id, self._agent.name)
        if existing:
            return existing

        # Default to project-style session key
        session_key = f"mc:{self._agent.org_slug}:project:{channel_id}"
        await self._state.create_session_mapping(
            session_key, self._agent.name, self._agent.org_slug,
            channel_id, "project",
        )
        log.info("router.session_created", channel=channel_id[:8], session=session_key)
        return session_key
