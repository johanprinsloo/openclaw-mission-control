"""
Main Bridge orchestrator.

Coordinates all components: SSE listeners, relay, state, health server.
Handles lifecycle: startup, shutdown, signal handling.
"""

from __future__ import annotations

import asyncio
import signal
import time
from typing import Any

import structlog

from .config import AgentConfig, BridgeConfig
from .health import HealthServer
from .metrics import MetricsCollector
from .relay import MessageRelay
from .router import EventRouter
from .sse_listener import SSEListener
from .state import BridgeState
from .subscriptions import SubscriptionManager

log = structlog.get_logger()

SHUTDOWN_TIMEOUT = 15.0


class CommsBridge:
    """
    Main bridge process: manages agent connections, event routing, and lifecycle.
    """

    def __init__(self, config: BridgeConfig):
        self._config = config
        self._metrics = MetricsCollector()
        self._state = BridgeState(config.state.db_path)
        self._relay = MessageRelay(
            mc_url=config.mission_control.url,
            gateway_url=config.gateway.url,
            verify_tls=config.mission_control.verify_tls,
            request_timeout=config.mission_control.request_timeout_seconds,
            metrics=self._metrics,
        )
        self._health = HealthServer(
            host=config.metrics.host,
            port=config.metrics.port,
            metrics=self._metrics,
        )
        self._listeners: list[SSEListener] = []
        self._routers: list[EventRouter] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the bridge: open state, relay, health server, and SSE listeners."""
        log.info("bridge.starting", agents=len(self._config.agents))

        await self._state.open()
        await self._relay.open()

        if self._config.metrics.enabled:
            try:
                await self._health.start()
                log.info(
                    "bridge.health_started",
                    host=self._config.metrics.host,
                    port=self._config.metrics.port,
                )
            except Exception as exc:
                log.warning("bridge.health_start_failed", error=str(exc))

        # Start one SSE listener + router per agent
        for agent_cfg in self._config.agents:
            api_key = agent_cfg.api_key
            if not api_key:
                log.error("bridge.missing_api_key", agent=agent_cfg.name, env=agent_cfg.api_key_env)
                continue

            subscriptions = SubscriptionManager()
            router = EventRouter(agent_cfg, self._state, self._relay, subscriptions)

            listener = SSEListener(
                mc_url=self._config.mission_control.url,
                agent_name=agent_cfg.name,
                api_key=api_key,
                org_slug=agent_cfg.org_slug,
                heartbeat_timeout=self._config.mission_control.sse_heartbeat_timeout_seconds,
                verify_tls=self._config.mission_control.verify_tls,
            )

            # Resume from persisted cursor
            cursor = await self._state.get_cursor(agent_cfg.name)
            if cursor:
                listener.set_last_event_id(cursor)
                log.info("bridge.resume_cursor", agent=agent_cfg.name, cursor=cursor)

            listener.on_event(router.handle_event)
            await listener.start()

            self._listeners.append(listener)
            self._routers.append(router)

            self._metrics.set_gauge("sse_connections_active", len(self._listeners))
            log.info("bridge.agent_started", agent=agent_cfg.name, org=agent_cfg.org_slug)

        self._running = True
        log.info("bridge.started", agents=len(self._listeners))

    async def stop(self) -> None:
        """Graceful shutdown: stop SSE, flush outbound, persist cursors, close connections."""
        if not self._running:
            return
        self._running = False
        log.info("bridge.stopping")

        # 1. Stop SSE listeners
        for listener in self._listeners:
            await listener.stop()
        log.info("bridge.sse_stopped")

        # 2. Flush outbound
        flushed = await self._relay.flush_outbound()
        if flushed:
            log.info("bridge.flushed_outbound", count=flushed)

        # 3. Close connections
        await self._health.stop()
        await self._relay.close()
        await self._state.close()

        log.info("bridge.stopped")

    async def run_forever(self) -> None:
        """Run until shutdown signal."""
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: self._shutdown_event.set())

        await self.start()

        # Periodic health status update
        try:
            while not self._shutdown_event.is_set():
                await self._update_health()
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            await asyncio.wait_for(self.stop(), timeout=SHUTDOWN_TIMEOUT)

    async def _update_health(self) -> None:
        agent_statuses = []
        for listener, agent_cfg in zip(self._listeners, self._config.agents):
            sessions = await self._state.list_sessions(agent_cfg.name)
            agent_statuses.append({
                "name": agent_cfg.name,
                "org": agent_cfg.org_slug,
                "sse_connected": listener.connected,
                "last_event_at": listener.last_event_at,
                "active_sessions": len(sessions),
                "reconnect_count": listener.reconnect_count,
            })

        gw_ok = await self._relay.check_gateway_health()
        mc_ok = await self._relay.check_mc_health()

        self._metrics.set_gauge("sse_connections_active", sum(
            1 for l in self._listeners if l.connected
        ))

        self._health.update_status(agent_statuses, gw_ok, mc_ok)
