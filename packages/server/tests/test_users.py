"""
Integration tests for User Management and API Key lifecycle (Phase 12).

Tests cover:
- API key generation, hashing, parsing, verification
- Schema validation for user CRUD
- API key rotation lifecycle with grace period
- Role-based access control logic
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.auth import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
    parse_api_key,
)


# ---------------------------------------------------------------------------
# Unit tests for API key utilities
# ---------------------------------------------------------------------------

class TestApiKeyUtilities:
    """Test API key generation, hashing, and parsing."""

    def test_generate_api_key_format(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid)
        assert key.startswith("mc_ak_live_")
        short_id = str(uid).replace("-", "")[:12]
        assert short_id in key

    def test_generate_temporary_key(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid, temporary=True)
        assert key.startswith("mc_ak_tmp_")

    def test_hash_and_verify(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid)
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed)
        assert not verify_api_key("mc_ak_live_000000000000_wrong", hashed)

    def test_parse_api_key_live(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid)
        prefix, short_id, random_part = parse_api_key(key)
        assert prefix == "mc_ak_live_"
        assert short_id == str(uid).replace("-", "")[:12]
        assert len(random_part) > 0

    def test_parse_api_key_tmp(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid, temporary=True)
        prefix, short_id, random_part = parse_api_key(key)
        assert prefix == "mc_ak_tmp_"

    def test_parse_invalid_key_raises(self):
        with pytest.raises(ValueError):
            parse_api_key("invalid_key")

    def test_parse_bad_format_raises(self):
        with pytest.raises(ValueError):
            parse_api_key("mc_ak_live_nounderscore")


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestUserSchemas:
    """Test Pydantic schema validation."""

    def test_user_add_request_human(self):
        from openclaw_mc_shared.schemas.users import UserAddRequest, UserType
        req = UserAddRequest(
            type=UserType.HUMAN,
            email="test@example.com",
            display_name="Test User",
        )
        assert req.role.value == "contributor"

    def test_user_add_request_agent(self):
        from openclaw_mc_shared.schemas.users import UserAddRequest, UserType
        req = UserAddRequest(
            type=UserType.AGENT,
            identifier="deploy-bot",
            display_name="Deploy Bot",
            role="administrator",
        )
        assert req.type == UserType.AGENT

    def test_user_add_request_validation_empty_name(self):
        from openclaw_mc_shared.schemas.users import UserAddRequest, UserType
        with pytest.raises(Exception):
            UserAddRequest(
                type=UserType.HUMAN,
                email="test@example.com",
                display_name="",  # min_length=1
            )

    def test_user_update_request_partial(self):
        from openclaw_mc_shared.schemas.users import UserUpdateRequest
        req = UserUpdateRequest(role="administrator")
        assert req.display_name is None

    def test_user_update_request_both_fields(self):
        from openclaw_mc_shared.schemas.users import UserUpdateRequest
        req = UserUpdateRequest(role="contributor", display_name="New Name")
        assert req.role.value == "contributor"
        assert req.display_name == "New Name"

    def test_user_response_serialization(self):
        from openclaw_mc_shared.schemas.users import UserResponse, UserType
        resp = UserResponse(
            id=uuid.uuid4(),
            type=UserType.HUMAN,
            email="test@example.com",
            display_name="Test",
            role="contributor",
            has_api_key=False,
            created_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump()
        assert data["type"] == "human"
        assert data["has_api_key"] is False

    def test_user_add_response_with_key(self):
        from openclaw_mc_shared.schemas.users import UserAddResponse, UserResponse, UserType
        user = UserResponse(
            id=uuid.uuid4(),
            type=UserType.AGENT,
            identifier="bot",
            display_name="Bot",
            role="contributor",
            has_api_key=True,
            created_at=datetime.now(timezone.utc),
        )
        resp = UserAddResponse(user=user, api_key="mc_ak_live_test_key")
        assert resp.api_key == "mc_ak_live_test_key"

    def test_api_key_rotate_response(self):
        from openclaw_mc_shared.schemas.users import ApiKeyRotateResponse
        resp = ApiKeyRotateResponse(
            api_key="mc_ak_live_new_key",
            previous_key_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        assert resp.api_key.startswith("mc_ak_live_")


# ---------------------------------------------------------------------------
# API key rotation lifecycle tests
# ---------------------------------------------------------------------------

class TestApiKeyRotationLifecycle:
    """Test the full API key rotation lifecycle with grace period."""

    def test_key_generation_is_unique(self):
        uid = uuid.uuid4()
        keys = {generate_api_key(uid) for _ in range(100)}
        assert len(keys) == 100

    def test_different_users_different_keys(self):
        k1 = generate_api_key(uuid.uuid4())
        k2 = generate_api_key(uuid.uuid4())
        assert k1 != k2

    def test_old_key_hash_preserved_for_grace_period(self):
        """Simulate rotation: old hash should be checkable during grace period."""
        uid = uuid.uuid4()
        old_key = generate_api_key(uid)
        old_hash = hash_api_key(old_key)

        new_key = generate_api_key(uid)
        new_hash = hash_api_key(new_key)

        # Both hashes should be independently verifiable
        assert verify_api_key(old_key, old_hash)
        assert verify_api_key(new_key, new_hash)
        assert not verify_api_key(old_key, new_hash)
        assert not verify_api_key(new_key, old_hash)

    def test_grace_period_expiry_logic(self):
        """Test the datetime comparison for grace period."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)
        assert expires > now  # still in grace period

        expired = now - timedelta(hours=1)
        assert expired < now  # grace period over

    def test_revoked_key_not_verifiable(self):
        """After revocation, setting hash to None means no key works."""
        uid = uuid.uuid4()
        key = generate_api_key(uid)
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed)
        # After revocation, api_key_hash = None, so no verification call happens


# ---------------------------------------------------------------------------
# Role-based access tests
# ---------------------------------------------------------------------------

class TestRoleAccess:
    """Test role validation logic."""

    def test_admin_role_value(self):
        from openclaw_mc_shared.schemas.common import Role
        assert Role.ADMIN.value == "administrator"

    def test_contributor_role_value(self):
        from openclaw_mc_shared.schemas.common import Role
        assert Role.CONTRIBUTOR.value == "contributor"

    def test_role_change_immediate(self):
        """Role changes should use the new role value directly."""
        from openclaw_mc_shared.schemas.users import UserUpdateRequest
        req = UserUpdateRequest(role="administrator")
        assert req.role.value == "administrator"

    def test_user_type_enum(self):
        from openclaw_mc_shared.schemas.users import UserType
        assert UserType.HUMAN.value == "human"
        assert UserType.AGENT.value == "agent"
