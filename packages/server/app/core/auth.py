"""
Authentication and Authorization for Mission Control.

Supports:
- Human auth: OIDC (GitHub/Google) placeholder + Email/Password for local dev
- Agent auth: API Key with O(1) lookup + sub-agent ephemeral keys
- JWT session management with Redis revocation list
- Role-based authorization dependencies
- Org-scoping for RLS
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
import structlog
from fastapi import Cookie, Depends, HTTPException, Request, WebSocket, Query
from fastapi.security import APIKeyHeader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import get_settings
from app.core.database import get_session
from app.core.redis import get_redis
from app.models.organization import Organization
from app.models.sub_agent import SubAgent
from app.models.user import User
from app.models.user_org import UserOrg

log = structlog.get_logger()
settings = get_settings()

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using bcrypt with cost factor 12."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# API Key generation & hashing
# ---------------------------------------------------------------------------

def generate_api_key(user_id: uuid.UUID, *, temporary: bool = False) -> str:
    """Generate a prefixed API key with embedded user hint for O(1) lookup."""
    prefix = "mc_ak_tmp_" if temporary else "mc_ak_live_"
    short_id = str(user_id).replace("-", "")[:12]
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}{short_id}_{random_part}"


def hash_api_key(key: str) -> str:
    """Hash an API key using bcrypt (cost 12)."""
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_api_key(key: str, hashed: str) -> bool:
    """Verify an API key against its bcrypt hash."""
    return bcrypt.checkpw(key.encode(), hashed.encode())


def parse_api_key(key: str) -> tuple[str, str, str]:
    """Parse an API key into (prefix, user_id_short, random).

    Returns (prefix, short_id, random_part).
    Raises ValueError if format is invalid.
    """
    if key.startswith("mc_ak_live_"):
        remainder = key[len("mc_ak_live_"):]
    elif key.startswith("mc_ak_tmp_"):
        remainder = key[len("mc_ak_tmp_"):]
    else:
        raise ValueError("Invalid API key prefix")

    prefix = key[:key.index(remainder)]
    parts = remainder.split("_", 1)
    if len(parts) != 2:
        raise ValueError("Invalid API key format")
    return prefix, parts[0], parts[1]


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_jwt(
    user_id: uuid.UUID,
    org_ids: list[str],
    active_org: str,
    role: str,
    *,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    """Create a signed JWT. Returns (token, jti)."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    payload = {
        "sub": str(user_id),
        "org_ids": org_ids,
        "active_org": active_org,
        "role": role,
        "iat": now,
        "exp": exp,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


# ---------------------------------------------------------------------------
# JWT Revocation (Redis)
# ---------------------------------------------------------------------------

async def revoke_jwt(jti: str, ttl_seconds: int = 3600) -> None:
    """Add a JWT ID to the revocation list in Redis."""
    redis = await get_redis()
    await redis.setex(f"jwt:revoked:{jti}", ttl_seconds, "1")


async def is_jwt_revoked(jti: str) -> bool:
    """Check if a JWT ID has been revoked."""
    redis = await get_redis()
    return await redis.exists(f"jwt:revoked:{jti}") > 0


# ---------------------------------------------------------------------------
# CSRF Token
# ---------------------------------------------------------------------------

def generate_csrf_token() -> str:
    """Generate a random CSRF token."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Authentication dependencies
# ---------------------------------------------------------------------------

class AuthenticatedUser:
    """Container for an authenticated user + their org context."""

    def __init__(self, user: User, org: Organization, user_org: UserOrg):
        self.user = user
        self.org = org
        self.user_org = user_org
        self.user_id = user.id
        self.org_id = org.id
        self.role = user_org.role


async def _resolve_org(org_slug: str, session: AsyncSession) -> Organization:
    """Resolve an org by slug, raise 404 if not found."""
    result = await session.execute(
        select(Organization).where(Organization.slug == org_slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def _authenticate_jwt(
    token: str, org: Organization, session: AsyncSession
) -> AuthenticatedUser:
    """Authenticate a user via JWT cookie."""
    try:
        payload = decode_jwt(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Check revocation
    jti = payload.get("jti")
    if jti and await is_jwt_revoked(jti):
        raise HTTPException(status_code=401, detail="Session has been revoked")

    user_id = uuid.UUID(payload["sub"])

    # Verify user is member of this org
    result = await session.execute(
        select(UserOrg).where(UserOrg.user_id == user_id, UserOrg.org_id == org.id)
    )
    user_org = result.scalar_one_or_none()
    if not user_org:
        print(f"DEBUG: UserOrg not found: user_id={user_id}, org_id={org.id}", flush=True)
        raise HTTPException(status_code=404, detail="Organization not found")
    
    print(f"DEBUG: UserOrg found: user_id={user_id}, org_id={org.id}, role={user_org.role}", flush=True)

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return AuthenticatedUser(user=user, org=org, user_org=user_org)


async def _authenticate_api_key(
    key: str, org: Organization, session: AsyncSession
) -> AuthenticatedUser:
    """Authenticate a user/agent via API key with O(1) lookup."""
    try:
        prefix, short_id, _ = parse_api_key(key)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid API key format")

    is_tmp = key.startswith("mc_ak_tmp_")

    if is_tmp:
        # Sub-agent ephemeral key — look up in sub_agents table
        result = await session.execute(
            select(SubAgent).where(
                SubAgent.org_id == org.id,
                SubAgent.status == "active",
            )
        )
        sub_agents = result.scalars().all()
        for sa in sub_agents:
            if sa.api_key_hash and verify_api_key(key, sa.api_key_hash):
                # Check expiry
                if sa.expires_at < datetime.now(timezone.utc):
                    raise HTTPException(status_code=401, detail="Ephemeral key expired")
                # Get the creating user's org membership for role
                result = await session.execute(
                    select(UserOrg).where(
                        UserOrg.user_id == sa.created_by,
                        UserOrg.org_id == org.id,
                    )
                )
                user_org = result.scalar_one_or_none()
                if not user_org:
                    raise HTTPException(status_code=401, detail="Sub-agent creator not in org")
                result = await session.execute(
                    select(User).where(User.id == sa.created_by)
                )
                user = result.scalar_one_or_none()
                if not user:
                    raise HTTPException(status_code=401, detail="User not found")
                return AuthenticatedUser(user=user, org=org, user_org=user_org)
        raise HTTPException(status_code=401, detail="Invalid API key")
    else:
        # Persistent agent key — O(1) lookup via short_id hint
        # Find all users whose ID starts with this prefix
        result = await session.execute(
            select(UserOrg).where(UserOrg.org_id == org.id)
        )
        user_orgs = result.scalars().all()
        for uo in user_orgs:
            uid_str = str(uo.user_id).replace("-", "")[:12]
            if uid_str == short_id:
                # Check current key
                if uo.api_key_hash and verify_api_key(key, uo.api_key_hash):
                    result = await session.execute(
                        select(User).where(User.id == uo.user_id)
                    )
                    user = result.scalar_one_or_none()
                    if not user:
                        raise HTTPException(status_code=401, detail="User not found")
                    return AuthenticatedUser(user=user, org=org, user_org=uo)
                # Check previous key (rotation grace period)
                if uo.api_key_previous_hash and uo.api_key_previous_expires_at:
                    from dateutil.parser import parse as parse_dt
                    try:
                        expires = datetime.fromisoformat(uo.api_key_previous_expires_at)
                    except (ValueError, TypeError):
                        expires = datetime.min.replace(tzinfo=timezone.utc)
                    if expires > datetime.now(timezone.utc) and verify_api_key(
                        key, uo.api_key_previous_hash
                    ):
                        result = await session.execute(
                            select(User).where(User.id == uo.user_id)
                        )
                        user = result.scalar_one_or_none()
                        if not user:
                            raise HTTPException(
                                status_code=401, detail="User not found"
                            )
                        return AuthenticatedUser(user=user, org=org, user_org=uo)

        raise HTTPException(status_code=401, detail="Invalid API key")


async def get_authenticated_user(
    request: Request,
    orgSlug: str,
    authorization: Optional[str] = Depends(api_key_header),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    """Main authentication dependency. Tries API key first, then JWT cookie."""
    org = await _resolve_org(orgSlug, session)

    # Set RLS org context (must use text() with f-string, not parameters)
    await session.execute(
        text(f"SET app.current_org_id = '{str(org.id)}'")
    )
    print(f"DEBUG: Set app.current_org_id = {org.id}", flush=True)

    # Try API key auth (agents)
    if authorization and authorization.startswith("Bearer "):
        key = authorization[7:].strip()
        if key.startswith("mc_ak_"):
            auth_user = await _authenticate_api_key(key, org, session)
            request.state.auth = auth_user
            print(f"DEBUG: API key auth: user={auth_user.user_id}, role={auth_user.role}", flush=True)
            return auth_user

    # Try JWT cookie auth (humans)
    token = request.cookies.get("mc_session")
    if token:
        auth_user = await _authenticate_jwt(token, org, session)
        request.state.auth = auth_user
        print(f"DEBUG: JWT auth: user={auth_user.user_id}, role={auth_user.role}", flush=True)
        return auth_user

    raise HTTPException(status_code=401, detail="Authentication required")


async def get_authenticated_user_ws(
    websocket: WebSocket,
    orgSlug: str,
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    """WebSocket authentication dependency."""
    org = await _resolve_org(orgSlug, session)
    # Set RLS org context (must use text() with f-string, not parameters)
    await session.execute(
        text(f"SET app.current_org_id = '{str(org.id)}'")
    )

    # Try query param (agents)
    if token and token.startswith("mc_ak_"):
        return await _authenticate_api_key(token, org, session)

    # Try cookie (humans)
    cookie_token = websocket.cookies.get("mc_session")
    if cookie_token:
        return await _authenticate_jwt(cookie_token, org, session)

    raise HTTPException(status_code=401, detail="Authentication required")


# ---------------------------------------------------------------------------
# Authorization dependencies (role checks)
# ---------------------------------------------------------------------------

async def require_member(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
) -> AuthenticatedUser:
    """Any org member can access this endpoint."""
    # If get_authenticated_user passed, user is a member
    return auth


async def require_contributor(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
) -> AuthenticatedUser:
    """Requires contributor or administrator role."""
    if auth.role not in ("contributor", "administrator"):
        raise HTTPException(status_code=403, detail="Contributor access required")
    return auth


async def require_admin(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
) -> AuthenticatedUser:
    """Requires administrator role."""
    print(f"DEBUG: require_admin check: user={auth.user_id}, role='{auth.role}'", flush=True)
    if auth.role != "administrator":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return auth


# ---------------------------------------------------------------------------
# Backward-compatible aliases for existing routers
# ---------------------------------------------------------------------------

async def get_current_org(
    orgSlug: str, session: AsyncSession = Depends(get_session)
) -> Organization:
    """Legacy dependency: resolve org by slug."""
    return await _resolve_org(orgSlug, session)


async def get_current_user(
    api_key: Optional[str] = Depends(api_key_header),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Legacy dependency: authenticate user (simple UUID-as-token for POC compat)."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API Key")

    token = api_key.replace("Bearer ", "").strip()

    # Try new API key format first
    if token.startswith("mc_ak_"):
        auth = await _authenticate_api_key(token, org, session)
        return auth.user

    # Fall back to POC UUID-as-token
    try:
        user_id = uuid.UUID(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid API Key format")

    result = await session.execute(
        select(UserOrg).where(UserOrg.user_id == user_id, UserOrg.org_id == org.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="User not authorized for this organization")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_user_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Legacy WebSocket auth dependency."""
    if not token:
        return None
    try:
        user_id = uuid.UUID(token)
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    except ValueError:
        return None
