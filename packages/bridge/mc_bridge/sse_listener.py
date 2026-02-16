"""
SSE listener for Mission Control event streams.

Maintains a persistent SSE connection per agent with:
- Automatic reconnection with exponential backoff
- Resume from last persisted event cursor (Last-Event-ID)
- Heartbeat timeout detection
- Graceful shutdown support
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import httpx
import structlog

log = structlog.get_logger()

# Reconnection parameters
RECONNECT_BASE_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 60.0
RECONNECT_MULTIPLIER = 2.0


@dataclass
class SSEEvent:
    """A parsed SSE event."""
    event_type: str
    data: dict[str, Any]
    sequence_id: str | None = None
    raw_id: str | None = None


EventHandler = Callable[[SSEEvent], Coroutine[Any, Any, None]]


class SSEListener:
    """
    Persistent SSE connection to Mission Control's event stream.

    Handles reconnection, heartbeat monitoring, and event dispatch.
    """

    def __init__(
        self,
        mc_url: str,
        agent_name: str,
        api_key: str,
        org_slug: str,
        heartbeat_timeout: float = 90.0,
        verify_tls: bool = True,
    ):
        self._mc_url = mc_url.rstrip("/")
        self._agent_name = agent_name
        self._api_key = api_key
        self._org_slug = org_slug
        self._heartbeat_timeout = heartbeat_timeout
        self._verify_tls = verify_tls

        self._handlers: list[EventHandler] = []
        self._running = False
        self._connected = False
        self._last_event_at: float | None = None
        self._last_event_id: str | None = None
        self._reconnect_count = 0
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_event_at(self) -> float | None:
        return self._last_event_at

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    def on_event(self, handler: EventHandler) -> None:
        """Register an event handler."""
        self._handlers.append(handler)

    def set_last_event_id(self, event_id: str) -> None:
        """Set the cursor for SSE resume (from persisted state)."""
        self._last_event_id = event_id

    async def start(self) -> None:
        """Start the SSE listener loop."""
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Gracefully stop the SSE listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        log.info("sse_listener.stopped", agent=self._agent_name)

    async def _listen_loop(self) -> None:
        backoff = RECONNECT_BASE_SECONDS

        while self._running:
            try:
                await self._connect_and_stream()
                backoff = RECONNECT_BASE_SECONDS  # Reset on clean disconnect
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                log.warning(
                    "sse_listener.connection_lost",
                    agent=self._agent_name,
                    error=str(exc),
                    backoff=backoff,
                )

            if not self._running:
                break

            self._reconnect_count += 1
            log.info(
                "sse_listener.reconnecting",
                agent=self._agent_name,
                backoff=backoff,
                attempt=self._reconnect_count,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * RECONNECT_MULTIPLIER, RECONNECT_MAX_SECONDS)

    async def _connect_and_stream(self) -> None:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "text/event-stream",
        }
        if self._last_event_id:
            headers["Last-Event-ID"] = self._last_event_id

        url = f"{self._mc_url}/api/v1/orgs/{self._org_slug}/events/stream"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(None),
            verify=self._verify_tls,
        ) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                self._connected = True
                self._last_event_at = time.time()
                log.info(
                    "sse_listener.connected",
                    agent=self._agent_name,
                    url=url,
                    resume_from=self._last_event_id,
                )

                current_event_type: str | None = None
                current_event_id: str | None = None
                current_data_lines: list[str] = []

                async for line in response.aiter_lines():
                    if not self._running:
                        break

                    line = line.rstrip("\n")
                    self._last_event_at = time.time()

                    if line.startswith("event:"):
                        current_event_type = line[6:].strip()
                    elif line.startswith("id:"):
                        current_event_id = line[3:].strip()
                    elif line.startswith("data:"):
                        current_data_lines.append(line[5:].strip())
                    elif line.startswith(":"):
                        # Comment / keepalive
                        pass
                    elif line == "":
                        # End of event — dispatch
                        if current_data_lines:
                            await self._dispatch_event(
                                current_event_type, current_event_id, current_data_lines
                            )
                        current_event_type = None
                        current_event_id = None
                        current_data_lines = []

    async def _dispatch_event(
        self,
        event_type: str | None,
        event_id: str | None,
        data_lines: list[str],
    ) -> None:
        data_str = "\n".join(data_lines)
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            log.warning("sse_listener.parse_error", data=data_str[:200])
            return

        resolved_type = event_type or data.get("type", "unknown")
        sequence_id = data.get("sequence_id")
        if sequence_id is not None:
            sequence_id = str(sequence_id)

        event = SSEEvent(
            event_type=resolved_type,
            data=data.get("payload", data),
            sequence_id=sequence_id,
            raw_id=event_id,
        )

        # Update cursor
        if event_id:
            self._last_event_id = event_id

        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                log.exception(
                    "sse_listener.handler_error",
                    agent=self._agent_name,
                    event_type=resolved_type,
                )
