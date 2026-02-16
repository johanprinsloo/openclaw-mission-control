"""
Shared fixtures for bridge integration tests.
"""

import asyncio
import os
import random
import tempfile

import pytest
import uvicorn

from .mock_servers import create_gateway_app, create_mc_app


class _UvicornServer:
    def __init__(self, app, host: str, port: int):
        self.config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(self.config)
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self.server.serve())
        for _ in range(100):
            if self.server.started:
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("Server did not start")

    async def stop(self):
        self.server.should_exit = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()


def _pick_port():
    return random.randint(19000, 19999)


@pytest.fixture
async def mc_server():
    port = _pick_port()
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    app = create_mc_app(db_path)
    srv = _UvicornServer(app, "127.0.0.1", port)
    await srv.start()
    yield f"http://127.0.0.1:{port}"
    await srv.stop()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
async def gw_server():
    port = _pick_port()
    app = create_gateway_app()
    srv = _UvicornServer(app, "127.0.0.1", port)
    await srv.start()
    yield f"http://127.0.0.1:{port}"
    await srv.stop()


@pytest.fixture
def bridge_config_dict(mc_server, gw_server, tmp_path):
    return {
        "mission_control": {
            "url": mc_server,
            "verify_tls": False,
            "request_timeout_seconds": 10,
        },
        "gateway": {
            "url": gw_server,
            "api_key_env": "TEST_GW_KEY",
        },
        "agents": [
            {
                "name": "test-agent",
                "api_key_env": "TEST_MC_API_KEY",
                "org_slug": "test-org",
                "auto_subscribe": True,
            }
        ],
        "state": {
            "db_path": str(tmp_path / "bridge_state.db"),
        },
        "logging": {"level": "debug", "format": "text"},
        "metrics": {"enabled": False, "port": _pick_port()},
    }
