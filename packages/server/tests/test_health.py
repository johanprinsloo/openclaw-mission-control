"""
Health check endpoint tests.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint should return status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_check(client: AsyncClient):
    """Ready endpoint should return status ready."""
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_api_root(client: AsyncClient):
    """API v1 root should return version and endpoint list."""
    response = await client.get("/api/v1/")
    assert response.status_code == 200
    data = response.json()
    assert data["api"] == "v1"
    assert "endpoints" in data
