"""
Tests for Authentication and Authorization (Phase 9).

Covers:
- Email/Password registration and login
- JWT creation, decoding, revocation
- API key generation, hashing, parsing
- Password hashing
- CSRF middleware
- Security headers middleware
- Role-based authorization (require_member, require_contributor, require_admin)
- Org-scoping
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.core.auth import (
    AuthenticatedUser,
    create_jwt,
    decode_jwt,
    generate_api_key,
    generate_csrf_token,
    hash_api_key,
    hash_password,
    parse_api_key,
    require_admin,
    require_contributor,
    require_member,
    verify_api_key,
    verify_password,
)
from app.core.middleware import CSRFMiddleware, SecurityHeadersMiddleware, SECURITY_HEADERS


# ---------------------------------------------------------------------------
# Unit Tests: Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "MySecureP@ssw0rd!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct-password")
        assert not verify_password("wrong-password", hashed)

    def test_different_hashes_for_same_password(self):
        """bcrypt uses random salt, so hashes differ."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        assert verify_password("same", h1)
        assert verify_password("same", h2)


# ---------------------------------------------------------------------------
# Unit Tests: API Key
# ---------------------------------------------------------------------------

class TestAPIKey:
    def test_generate_persistent_key(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid, temporary=False)
        assert key.startswith("mc_ak_live_")
        short = str(uid).replace("-", "")[:12]
        assert short in key

    def test_generate_temporary_key(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid, temporary=True)
        assert key.startswith("mc_ak_tmp_")

    def test_hash_and_verify_key(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid)
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed)
        assert not verify_api_key("mc_ak_live_wrong_key", hashed)

    def test_parse_key(self):
        uid = uuid.uuid4()
        key = generate_api_key(uid)
        prefix, short_id, random_part = parse_api_key(key)
        assert prefix == "mc_ak_live_"
        assert short_id == str(uid).replace("-", "")[:12]
        assert len(random_part) > 0

    def test_parse_invalid_prefix(self):
        with pytest.raises(ValueError, match="Invalid API key prefix"):
            parse_api_key("invalid_key_format")

    def test_parse_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid API key format"):
            parse_api_key("mc_ak_live_nounderscore")


# ---------------------------------------------------------------------------
# Unit Tests: JWT
# ---------------------------------------------------------------------------

class TestJWT:
    def test_create_and_decode(self):
        uid = uuid.uuid4()
        token, jti = create_jwt(
            user_id=uid,
            org_ids=["org1"],
            active_org="org1",
            role="contributor",
        )
        payload = decode_jwt(token)
        assert payload["sub"] == str(uid)
        assert payload["org_ids"] == ["org1"]
        assert payload["active_org"] == "org1"
        assert payload["role"] == "contributor"
        assert payload["jti"] == jti

    def test_expired_jwt_raises(self):
        uid = uuid.uuid4()
        token, _ = create_jwt(
            user_id=uid,
            org_ids=[],
            active_org="org1",
            role="contributor",
            expires_delta=timedelta(seconds=-1),
        )
        import jwt as pyjwt
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_jwt(token)

    def test_tampered_jwt_raises(self):
        uid = uuid.uuid4()
        token, _ = create_jwt(
            user_id=uid, org_ids=[], active_org="org1", role="contributor"
        )
        tampered = token[:-5] + "XXXXX"
        import jwt as pyjwt
        with pytest.raises(pyjwt.InvalidSignatureError):
            decode_jwt(tampered)


# ---------------------------------------------------------------------------
# Unit Tests: CSRF Token
# ---------------------------------------------------------------------------

class TestCSRFToken:
    def test_generates_unique_tokens(self):
        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert t1 != t2
        assert len(t1) > 20


# ---------------------------------------------------------------------------
# Integration Tests: Middleware
# ---------------------------------------------------------------------------

class TestSecurityHeadersMiddleware:
    def test_headers_present(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        for header, value in SECURITY_HEADERS.items():
            assert resp.headers.get(header) == value


class TestCSRFMiddleware:
    def _make_app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(CSRFMiddleware)

        @app.get("/test")
        async def get_test():
            return {"ok": True}

        @app.post("/test")
        async def post_test():
            return {"ok": True}

        return app

    def test_get_passes_without_csrf(self):
        client = TestClient(self._make_app())
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_post_with_api_key_skips_csrf(self):
        client = TestClient(self._make_app())
        resp = client.post("/test", headers={"Authorization": "Bearer mc_ak_live_xxx"})
        assert resp.status_code == 200

    def test_post_without_session_cookie_passes(self):
        """No session cookie = not a browser request, skip CSRF."""
        client = TestClient(self._make_app())
        resp = client.post("/test")
        assert resp.status_code == 200

    def test_post_with_session_but_no_csrf_fails(self):
        client = TestClient(self._make_app(), cookies={"mc_session": "some-jwt"})
        resp = client.post("/test")
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["error"]["code"]

    def test_post_with_matching_csrf_passes(self):
        csrf_token = "test-csrf-token"
        client = TestClient(
            self._make_app(),
            cookies={"mc_session": "some-jwt", "mc_csrf": csrf_token},
        )
        resp = client.post("/test", headers={"X-CSRF-Token": csrf_token})
        assert resp.status_code == 200

    def test_post_with_mismatched_csrf_fails(self):
        client = TestClient(
            self._make_app(),
            cookies={"mc_session": "some-jwt", "mc_csrf": "token-a"},
        )
        resp = client.post("/test", headers={"X-CSRF-Token": "token-b"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Integration Tests: Auth Endpoints
# ---------------------------------------------------------------------------

class TestAuthEndpoints:
    """Tests for /auth/* endpoints using the real app with mocked DB."""

    @pytest.fixture
    def app(self):
        """Create a test app with auth routes (isolated, no other v1 routers)."""
        import importlib
        import sys
        # Import auth module directly to avoid triggering v1/__init__ which needs shared pkg
        spec = importlib.util.spec_from_file_location(
            "app.api.v1.auth",
            "app/api/v1/auth.py",
            submodule_search_locations=[],
        )
        # Use already-imported module if available
        if "app.api.v1.auth" in sys.modules:
            auth_mod = sys.modules["app.api.v1.auth"]
        else:
            auth_mod = importlib.util.module_from_spec(spec)
            sys.modules["app.api.v1.auth"] = auth_mod
            spec.loader.exec_module(auth_mod)

        test_app = FastAPI()
        test_app.include_router(auth_mod.router, prefix="/auth")
        return test_app

    # NOTE: Full integration tests for register/login require a running DB.
    # These are covered in test_auth_integration.py.
    # Here we test the endpoint wiring and validation.

    @pytest.mark.skipif(
        True,  # Skip when no DB available
        reason="Requires running PostgreSQL + greenlet for async session"
    )
    def test_register_short_password(self, app):
        """Password < 8 chars should fail."""
        client = TestClient(app)
        resp = client.post(
            "/auth/register",
            json={"email": "test@example.com", "password": "short", "display_name": "Test"},
        )
        assert resp.status_code == 400

    def test_oidc_login_placeholder(self, app):
        client = TestClient(app)
        resp = client.get("/auth/login/oidc?provider=github")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "github"
        assert data["status"] == "placeholder"
        assert "github.com" in data["authorization_url"]

    def test_oidc_login_bad_provider(self, app):
        client = TestClient(app)
        resp = client.get("/auth/login/oidc?provider=facebook")
        assert resp.status_code == 400

    def test_logout_clears_cookies(self, app):
        client = TestClient(app)
        resp = client.post("/auth/logout")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out"


# ---------------------------------------------------------------------------
# Unit Tests: Role-based auth matrix
# ---------------------------------------------------------------------------

class TestAuthorizationMatrix:
    """
    Verify that role dependencies enforce correct access levels.

    Uses mock AuthenticatedUser objects to test the dependency functions directly.
    """

    def _mock_auth(self, role: str) -> AuthenticatedUser:
        from unittest.mock import MagicMock
        user = MagicMock()
        user.id = uuid.uuid4()
        org = MagicMock()
        org.id = uuid.uuid4()
        user_org = MagicMock()
        user_org.role = role
        return AuthenticatedUser(user=user, org=org, user_org=user_org)

    @pytest.mark.asyncio
    async def test_member_allows_all_roles(self):
        for role in ("administrator", "contributor", "member"):
            auth = self._mock_auth(role)
            result = await require_member(auth)
            assert result == auth

    @pytest.mark.asyncio
    async def test_contributor_allows_contributor_and_admin(self):
        for role in ("administrator", "contributor"):
            auth = self._mock_auth(role)
            result = await require_contributor(auth)
            assert result == auth

    @pytest.mark.asyncio
    async def test_contributor_rejects_member(self):
        auth = self._mock_auth("member")
        with pytest.raises(Exception) as exc_info:
            await require_contributor(auth)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allows_admin(self):
        auth = self._mock_auth("administrator")
        result = await require_admin(auth)
        assert result == auth

    @pytest.mark.asyncio
    async def test_admin_rejects_contributor(self):
        auth = self._mock_auth("contributor")
        with pytest.raises(Exception) as exc_info:
            await require_admin(auth)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_rejects_member(self):
        auth = self._mock_auth("member")
        with pytest.raises(Exception) as exc_info:
            await require_admin(auth)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Unit Tests: JWT Revocation (mocked Redis)
# ---------------------------------------------------------------------------

class TestJWTRevocation:
    @pytest.mark.asyncio
    async def test_revoke_and_check(self):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)

        with patch("app.core.auth.get_redis", return_value=mock_redis):
            from app.core.auth import revoke_jwt, is_jwt_revoked

            await revoke_jwt("test-jti-123")
            mock_redis.setex.assert_called_once_with("jwt:revoked:test-jti-123", 3600, "1")

            result = await is_jwt_revoked("test-jti-123")
            assert result is True

    @pytest.mark.asyncio
    async def test_non_revoked_jwt(self):
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)

        with patch("app.core.auth.get_redis", return_value=mock_redis):
            from app.core.auth import is_jwt_revoked
            result = await is_jwt_revoked("non-existent-jti")
            assert result is False
