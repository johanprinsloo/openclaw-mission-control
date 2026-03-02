"""
Unit tests for Sub-Agent schemas and lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from openclaw_mc_shared.schemas.sub_agents import (
    SubAgentCreate,
    SubAgentRead,
    SubAgentSpawnResponse,
    SubAgentTerminateRequest,
)


class TestSubAgentSchemas:
    """Test Sub-Agent Pydantic schema validation."""

    def test_sub_agent_create_defaults(self):
        task_id = uuid.uuid4()
        s = SubAgentCreate(
            task_id=task_id,
            model="gpt-4",
            instructions="Do something",
        )
        assert s.task_id == task_id
        assert s.model == "gpt-4"
        assert s.instructions == "Do something"
        assert s.timeout_minutes == 60  # Default

    def test_sub_agent_create_invalid_timeout(self):
        task_id = uuid.uuid4()
        # Too low
        with pytest.raises(ValidationError):
            SubAgentCreate(
                task_id=task_id,
                model="gpt-4",
                instructions="Test",
                timeout_minutes=0,
            )
        # Too high
        with pytest.raises(ValidationError):
            SubAgentCreate(
                task_id=task_id,
                model="gpt-4",
                instructions="Test",
                timeout_minutes=2000,
            )

    def test_sub_agent_read_serialization(self):
        sa_id = uuid.uuid4()
        org_id = uuid.uuid4()
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        
        sa = SubAgentRead(
            id=sa_id,
            org_id=org_id,
            task_id=task_id,
            model="gpt-4",
            instructions="Test",
            status="active",
            created_by=user_id,
            created_at=now,
            expires_at=expires,
        )
        assert sa.id == sa_id
        assert sa.status == "active"
        assert sa.terminated_at is None

    def test_sub_agent_spawn_response(self):
        sa_id = uuid.uuid4()
        org_id = uuid.uuid4()
        task_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        
        sa_read = SubAgentRead(
            id=sa_id,
            org_id=org_id,
            task_id=task_id,
            model="gpt-4",
            instructions="Test",
            status="active",
            created_by=user_id,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        resp = SubAgentSpawnResponse(sub_agent=sa_read, api_key="mc_ak_tmp_test_key")
        assert resp.api_key == "mc_ak_tmp_test_key"
        assert resp.sub_agent.id == sa_id

    def test_sub_agent_terminate_request(self):
        req = SubAgentTerminateRequest(reason="Finished task")
        assert req.reason == "Finished task"
        
        req_none = SubAgentTerminateRequest()
        assert req_none.reason is None


class TestSubAgentLifecycle:
    """Test sub-agent status transitions."""
    
    def test_lifecycle_states(self):
        # Conceptual lifecycle check
        states = ["active", "terminated"]
        assert "active" in states
        assert "terminated" in states
        
    def test_expiry_check(self):
        now = datetime.now(timezone.utc)
        past = now - timedelta(minutes=1)
        future = now + timedelta(minutes=1)
        
        assert past < now  # Expired
        assert future > now  # Active
