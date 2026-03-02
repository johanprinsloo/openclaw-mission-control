"""
Integration tests for Sub-Agent API endpoints using mock dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.api.v1.sub_agents import router
from app.core.auth import AuthenticatedUser, require_contributor, require_member
from app.core.database import get_session
from app.models.sub_agent import SubAgent
from openclaw_mc_shared.schemas.sub_agents import SubAgentCreate, SubAgentTerminateRequest


@pytest.fixture
def mock_auth():
    user = AsyncMock()
    user.id = uuid.uuid4()
    org = AsyncMock()
    org.id = uuid.uuid4()
    user_org = AsyncMock()
    user_org.role = "administrator"
    return AuthenticatedUser(user=user, org=org, user_org=user_org)


class TestSubAgentAPI:
    """Test Sub-Agent API endpoints with mocked service layer."""

    @pytest.mark.asyncio
    async def test_spawn_sub_agent_endpoint(self, mock_auth):
        from app.api.v1.sub_agents import router
        
        spawn_req = SubAgentCreate(
            task_id=uuid.uuid4(),
            model="gpt-4",
            instructions="Test spawn",
        )
        
        mock_sa = SubAgent(
            id=uuid.uuid4(),
            org_id=mock_auth.org_id,
            task_id=spawn_req.task_id,
            model=spawn_req.model,
            instructions=spawn_req.instructions,
            status="active",
            created_by=mock_auth.user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        with patch("app.api.v1.sub_agents.spawn_sub_agent", return_value=(mock_sa, "mc_ak_tmp_test")):
            with patch("app.api.v1.sub_agents.broadcast_event", new_callable=AsyncMock):
                app = FastAPI()
                app.include_router(router, prefix="/orgs/{orgSlug}/sub-agents")
                
                # Mock dependencies for the router
                app.dependency_overrides[require_contributor] = lambda: mock_auth
                app.dependency_overrides[get_session] = lambda: AsyncMock()

                client = TestClient(app)
                resp = client.post(
                    f"/orgs/test-org/sub-agents/",
                    json=spawn_req.model_dump(mode="json"),
                )
                
                assert resp.status_code == 201
                data = resp.json()
                assert data["api_key"] == "mc_ak_tmp_test"
                assert data["sub_agent"]["id"] == str(mock_sa.id)

    @pytest.mark.asyncio
    async def test_list_sub_agents_endpoint(self, mock_auth):
        from app.api.v1.sub_agents import router
        
        mock_sa = SubAgent(
            id=uuid.uuid4(),
            org_id=mock_auth.org_id,
            task_id=uuid.uuid4(),
            model="gpt-4",
            instructions="Test list",
            status="active",
            created_by=mock_auth.user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        with patch("app.api.v1.sub_agents.list_sub_agents", return_value=[mock_sa]):
            app = FastAPI()
            app.include_router(router, prefix="/orgs/{orgSlug}/sub-agents")
            app.dependency_overrides[require_member] = lambda: mock_auth
            app.dependency_overrides[get_session] = lambda: AsyncMock()

            client = TestClient(app)
            resp = client.get("/orgs/test-org/sub-agents/")
            
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["id"] == str(mock_sa.id)

    @pytest.mark.asyncio
    async def test_terminate_sub_agent_endpoint(self, mock_auth):
        from app.api.v1.sub_agents import router
        
        sa_id = uuid.uuid4()
        mock_sa = SubAgent(
            id=sa_id,
            org_id=mock_auth.org_id,
            task_id=uuid.uuid4(),
            model="gpt-4",
            instructions="Test terminate",
            status="terminated",
            created_by=mock_auth.user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            terminated_at=datetime.now(timezone.utc),
            termination_reason="Finished",
        )

        terminate_req = SubAgentTerminateRequest(reason="Finished")

        with patch("app.api.v1.sub_agents.terminate_sub_agent", return_value=mock_sa):
            with patch("app.api.v1.sub_agents.broadcast_event", new_callable=AsyncMock):
                app = FastAPI()
                app.include_router(router, prefix="/orgs/{orgSlug}/sub-agents")
                app.dependency_overrides[require_contributor] = lambda: mock_auth
                app.dependency_overrides[get_session] = lambda: AsyncMock()

                client = TestClient(app)
                resp = client.post(
                    f"/orgs/test-org/sub-agents/{sa_id}/terminate",
                    json=terminate_req.model_dump(mode="json"),
                )
                
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "terminated"
                assert data["termination_reason"] == "Finished"
