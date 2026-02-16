"""
Health and metrics HTTP server.

Exposes:
- GET /health — JSON health status
- GET /metrics — Prometheus-compatible metrics
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aiohttp import web

from .metrics import MetricsCollector


class HealthServer:
    """Lightweight HTTP server for health checks and metrics."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9090,
        metrics: MetricsCollector | None = None,
    ):
        self._host = host
        self._port = port
        self._metrics = metrics or MetricsCollector()
        self._agent_statuses: list[dict[str, Any]] = []
        self._gateway_reachable = False
        self._mc_reachable = False
        self._runner: web.AppRunner | None = None

    def update_status(
        self,
        agent_statuses: list[dict[str, Any]],
        gateway_reachable: bool,
        mc_reachable: bool,
    ) -> None:
        self._agent_statuses = agent_statuses
        self._gateway_reachable = gateway_reachable
        self._mc_reachable = mc_reachable

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health_handler)
        app.router.add_get("/metrics", self._metrics_handler)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _health_handler(self, request: web.Request) -> web.Response:
        status = "healthy" if self._mc_reachable else "degraded"
        body = {
            "status": status,
            "agents": self._agent_statuses,
            "gateway_reachable": self._gateway_reachable,
            "mission_control_reachable": self._mc_reachable,
        }
        return web.json_response(body)

    async def _metrics_handler(self, request: web.Request) -> web.Response:
        return web.Response(
            text=self._metrics.to_prometheus(),
            content_type="text/plain",
        )
