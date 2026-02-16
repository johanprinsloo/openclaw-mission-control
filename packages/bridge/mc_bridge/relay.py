"""
Message relay: translates between Mission Control and OpenClaw Gateway.

Handles:
- Inbound: MC channel message → Gateway session message
- Outbound: Gateway response → MC channel POST
- Rate limiting and retry logic
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import httpx
import structlog

from .metrics import MetricsCollector

log = structlog.get_logger()

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 1.0
OUTBOUND_BUFFER_MAX = 1000


class MessageRelay:
    """
    Relays messages between Mission Control and the OpenClaw Gateway.

    Handles retry logic, rate limiting (429), and bounded buffering when
    the Gateway is unreachable.
    """

    def __init__(
        self,
        mc_url: str,
        gateway_url: str,
        verify_tls: bool = True,
        request_timeout: int = 30,
        metrics: MetricsCollector | None = None,
    ):
        self._mc_url = mc_url.rstrip("/")
        self._gateway_url = gateway_url.rstrip("/")
        self._verify_tls = verify_tls
        self._request_timeout = request_timeout
        self._metrics = metrics
        self._client: httpx.AsyncClient | None = None
        self._outbound_buffer: deque = deque(maxlen=OUTBOUND_BUFFER_MAX)

    async def open(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._request_timeout),
            verify=self._verify_tls,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def flush_outbound(self) -> int:
        """Flush any buffered outbound messages. Returns count flushed."""
        flushed = 0
        while self._outbound_buffer:
            item = self._outbound_buffer.popleft()
            try:
                await self._post_to_mc(
                    item["channel_id"],
                    item["content"],
                    item["sender_id"],
                    item["sender_name"],
                    item["api_key"],
                    item["org_slug"],
                )
                flushed += 1
            except Exception:
                log.warning("relay.flush_failed", channel_id=item["channel_id"])
                break
        return flushed

    # --- Inbound: MC → Gateway ---

    async def forward_to_gateway(
        self,
        session_key: str,
        message: str,
        sender: str,
    ) -> str | None:
        """Send a message to the Gateway and return the agent's response."""
        assert self._client
        try:
            resp = await self._client.post(
                f"{self._gateway_url}/v1/chat",
                json={
                    "session_key": session_key,
                    "message": message,
                    "sender": sender,
                },
            )
            resp.raise_for_status()
            if self._metrics:
                self._metrics.inc("messages_inbound_total")
            return resp.json().get("response")
        except httpx.HTTPStatusError as exc:
            log.error(
                "relay.gateway_error",
                status=exc.response.status_code,
                session_key=session_key,
            )
            return None
        except httpx.ConnectError:
            log.error("relay.gateway_unreachable", session_key=session_key)
            return None

    async def forward_command_to_gateway(
        self,
        session_key: str,
        command: str,
        args: str = "",
    ) -> str | None:
        """Send a command to the Gateway and return the output."""
        assert self._client
        try:
            resp = await self._client.post(
                f"{self._gateway_url}/v1/command",
                json={
                    "session_key": session_key,
                    "command": command,
                    "args": args,
                },
            )
            resp.raise_for_status()
            if self._metrics:
                self._metrics.inc("commands_routed_total")
            return resp.json().get("output")
        except httpx.HTTPStatusError as exc:
            log.error(
                "relay.gateway_command_error",
                status=exc.response.status_code,
                command=command,
            )
            return None
        except httpx.ConnectError:
            log.error("relay.gateway_unreachable_cmd", command=command)
            return None

    # --- Outbound: Gateway response → MC ---

    async def post_to_mc(
        self,
        channel_id: str,
        content: str,
        sender_id: str,
        sender_name: str,
        api_key: str,
        org_slug: str,
    ) -> bool:
        """Post a message to a Mission Control channel with retries."""
        try:
            await self._post_to_mc(
                channel_id, content, sender_id, sender_name, api_key, org_slug
            )
            return True
        except Exception:
            # Buffer for later flush
            self._outbound_buffer.append({
                "channel_id": channel_id,
                "content": content,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "api_key": api_key,
                "org_slug": org_slug,
            })
            return False

    async def _post_to_mc(
        self,
        channel_id: str,
        content: str,
        sender_id: str,
        sender_name: str,
        api_key: str,
        org_slug: str,
    ) -> None:
        assert self._client
        url = f"{self._mc_url}/api/v1/channels/{channel_id}/messages"
        body = {
            "content": content,
            "sender_id": sender_id,
            "sender_name": sender_name,
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._client.post(url, json=body, headers=headers)

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", RETRY_BASE_SECONDS * (attempt + 1)))
                    log.warning("relay.rate_limited", retry_after=retry_after)
                    await asyncio.sleep(retry_after)
                    continue

                resp.raise_for_status()
                if self._metrics:
                    self._metrics.inc("messages_outbound_total")
                return

            except httpx.HTTPStatusError as exc:
                if 400 <= exc.response.status_code < 500:
                    log.error(
                        "relay.mc_client_error",
                        status=exc.response.status_code,
                        channel_id=channel_id,
                    )
                    if self._metrics:
                        self._metrics.inc("messages_outbound_errors_total")
                    raise  # Don't retry 4xx
                last_exc = exc
            except (httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = exc

            backoff = RETRY_BASE_SECONDS * (2 ** attempt)
            log.warning(
                "relay.mc_retry",
                attempt=attempt + 1,
                backoff=backoff,
                error=str(last_exc),
            )
            await asyncio.sleep(backoff)

        if self._metrics:
            self._metrics.inc("messages_outbound_errors_total")
        if last_exc:
            raise last_exc

    # --- Health ---

    async def check_gateway_health(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get(f"{self._gateway_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def check_mc_health(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get(f"{self._mc_url}/health")
            return resp.status_code == 200
        except Exception:
            return False
