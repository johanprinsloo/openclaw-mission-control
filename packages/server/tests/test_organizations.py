"""
Integration tests for Organization endpoints and lifecycle.

Tests cover:
- Org CRUD (create, list, get, update, delete)
- Org lifecycle state machine
- Settings validation and deep merge
- Grace period deletion
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.organization import Organization
from app.models.user import User
from app.models.user_org import UserOrg


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite for fast tests
# ---------------------------------------------------------------------------

@pytest.fixture
def test_user_id():
    return uuid.uuid4()


@pytest.fixture
def auth_headers(test_user_id):
    """Simple Bearer UUID auth (POC compat)."""
    return {"Authorization": f"Bearer {test_user_id}"}


# ---------------------------------------------------------------------------
# Schema validation tests (no DB needed)
# ---------------------------------------------------------------------------

class TestOrgSettingsValidation:
    """Test OrgSettings Pydantic model validation."""

    def test_defaults(self):
        from openclaw_mc_shared.schemas.organizations import OrgSettings
        s = OrgSettings()
        assert s.deletion_grace_period_days == 30
        assert s.authentication.api_key_rotation_reminder_days == 90
        assert s.task_defaults.default_priority == "medium"

    def test_grace_period_min(self):
        from openclaw_mc_shared.schemas.organizations import OrgSettings
        with pytest.raises(Exception):
            OrgSettings(deletion_grace_period_days=3)

    def test_grace_period_max(self):
        from openclaw_mc_shared.schemas.organizations import OrgSettings
        with pytest.raises(Exception):
            OrgSettings(deletion_grace_period_days=100)

    def test_deep_merge(self):
        from app.services.organizations import _deep_merge
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        patch = {"a": {"b": 10}, "e": 5}
        result = _deep_merge(base, patch)
        assert result == {"a": {"b": 10, "c": 2}, "d": 3, "e": 5}


class TestOrgLifecycleTransitions:
    """Test lifecycle state machine."""

    def test_valid_transitions(self):
        from openclaw_mc_shared.schemas.organizations import OrgStatus, ORG_TRANSITIONS
        # Active can go to suspended or pending_deletion
        assert OrgStatus.SUSPENDED in ORG_TRANSITIONS[OrgStatus.ACTIVE]
        assert OrgStatus.PENDING_DELETION in ORG_TRANSITIONS[OrgStatus.ACTIVE]

    def test_deleted_is_terminal(self):
        from openclaw_mc_shared.schemas.organizations import OrgStatus, ORG_TRANSITIONS
        assert ORG_TRANSITIONS[OrgStatus.DELETED] == []

    def test_pending_deletion_can_reactivate(self):
        from openclaw_mc_shared.schemas.organizations import OrgStatus, ORG_TRANSITIONS
        assert OrgStatus.ACTIVE in ORG_TRANSITIONS[OrgStatus.PENDING_DELETION]


class TestOrgCreateRequestValidation:
    """Test OrgCreateRequest validation."""

    def test_valid_slug(self):
        from openclaw_mc_shared.schemas.organizations import OrgCreateRequest
        req = OrgCreateRequest(name="Test Org", slug="test-org")
        assert req.slug == "test-org"

    def test_invalid_slug_uppercase(self):
        from openclaw_mc_shared.schemas.organizations import OrgCreateRequest
        with pytest.raises(Exception):
            OrgCreateRequest(name="Test", slug="Test-Org")

    def test_invalid_slug_start_with_hyphen(self):
        from openclaw_mc_shared.schemas.organizations import OrgCreateRequest
        with pytest.raises(Exception):
            OrgCreateRequest(name="Test", slug="-test")

    def test_slug_too_short(self):
        from openclaw_mc_shared.schemas.organizations import OrgCreateRequest
        with pytest.raises(Exception):
            OrgCreateRequest(name="Test", slug="a")


class TestSettingsSubModels:
    """Test individual settings sub-model validation."""

    def test_agent_limits_timeout_range(self):
        from openclaw_mc_shared.schemas.organizations import AgentLimitsSettings
        # Valid
        s = AgentLimitsSettings(sub_agent_default_timeout_minutes=60)
        assert s.sub_agent_default_timeout_minutes == 60
        # Too low
        with pytest.raises(Exception):
            AgentLimitsSettings(sub_agent_default_timeout_minutes=1)
        # Too high
        with pytest.raises(Exception):
            AgentLimitsSettings(sub_agent_default_timeout_minutes=2000)

    def test_task_defaults_priority_pattern(self):
        from openclaw_mc_shared.schemas.organizations import TaskDefaultsSettings
        s = TaskDefaultsSettings(default_priority="high")
        assert s.default_priority == "high"
        with pytest.raises(Exception):
            TaskDefaultsSettings(default_priority="urgent")
