"""
Authentication endpoints.

- Email/Password registration & login (local dev + production)
- OIDC login placeholder (GitHub/Google)
- JWT session management (refresh, logout)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.auth import (
    AuthenticatedUser,
    create_jwt,
    decode_jwt,
    generate_csrf_token,
    hash_password,
    is_jwt_revoked,
    revoke_jwt,
    verify_password,
)
from app.core.config import get_settings
from app.core.database import get_session
from app.models.organization import Organization
from app.models.user import User
from app.models.user_org import UserOrg

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()

# Cookie config
COOKIE_KWARGS = {
    "httponly": True,
    "secure": not settings.debug,  # allow non-HTTPS in dev
    "samesite": "lax",
    "path": "/",
    "max_age": settings.jwt_expire_minutes * 60,
}


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    """Set the session JWT and CSRF cookies on a response."""
    response.set_cookie(key="mc_session", value=token, **COOKIE_KWARGS)
    response.set_cookie(
        key="mc_csrf",
        value=csrf,
        httponly=False,  # JS must read this
        secure=not settings.debug,
        samesite="lax",
        path="/",
        max_age=settings.jwt_expire_minutes * 60,
    )


# ---------------------------------------------------------------------------
# Email/Password Registration
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    message: str


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user with email/password. Creates a default org in single-tenant mode."""
    # Check if email already exists
    result = await session.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Validate password strength (basic)
    if len(body.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        type="human",
        password_hash=hash_password(body.password),
    )
    session.add(user)

    # In single-tenant mode, auto-create a default org or add to existing
    if settings.deployment_mode == "single-tenant":
        result = await session.execute(
            select(Organization).where(Organization.slug == "default")
        )
        org = result.scalar_one_or_none()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Default Organization",
                slug="default",
                status="active",
                settings={},
            )
            session.add(org)
            role = "administrator"  # First user is admin
        else:
            # Check if there are any admins
            result = await session.execute(
                select(UserOrg).where(
                    UserOrg.org_id == org.id, UserOrg.role == "administrator"
                )
            )
            role = "administrator" if not result.scalars().first() else "contributor"

        user_org = UserOrg(
            user_id=user.id,
            org_id=org.id,
            role=role,
            display_name=body.display_name,
        )
        session.add(user_org)

        await session.flush()

        # Issue JWT
        token, _jti = create_jwt(
            user_id=user.id,
            org_ids=[str(org.id)],
            active_org=str(org.id),
            role=role,
        )
        csrf = generate_csrf_token()
        _set_session_cookies(response, token, csrf)
    else:
        await session.flush()

    log.info("user.registered", user_id=str(user.id), email=body.email)
    return AuthResponse(
        user_id=str(user.id),
        email=body.email,
        message="Registration successful",
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate with email/password and receive a JWT session."""
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(body.password, user.password_hash):
        log.warning("auth.login_failure", email=body.email, reason="bad_password")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Get user's org memberships
    result = await session.execute(
        select(UserOrg).where(UserOrg.user_id == user.id)
    )
    user_orgs = result.scalars().all()

    if not user_orgs:
        raise HTTPException(status_code=403, detail="User has no organization memberships")

    first_uo = user_orgs[0]
    org_ids = [str(uo.org_id) for uo in user_orgs]

    token, _jti = create_jwt(
        user_id=user.id,
        org_ids=org_ids,
        active_org=str(first_uo.org_id),
        role=first_uo.role,
    )
    csrf = generate_csrf_token()
    _set_session_cookies(response, token, csrf)

    log.info("auth.login_success", user_id=str(user.id), email=body.email)
    return AuthResponse(
        user_id=str(user.id),
        email=body.email,
        message="Login successful",
    )


# ---------------------------------------------------------------------------
# OIDC Login (Placeholder)
# ---------------------------------------------------------------------------

@router.get("/login/oidc")
async def oidc_login(provider: str):
    """
    Initiate OIDC login flow.

    Placeholder — in production this redirects to the provider's authorization endpoint.
    """
    if provider not in ("github", "google"):
        raise HTTPException(status_code=400, detail="Unsupported OIDC provider")

    # In production: build authorization URL and redirect
    # For now, return the URL that would be used
    if provider == "github":
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={settings.github_client_id}"
            f"&scope=read:user user:email"
        )
    else:
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={settings.google_client_id}"
            f"&response_type=code"
            f"&scope=openid email profile"
        )

    return {"provider": provider, "authorization_url": auth_url, "status": "placeholder"}


@router.get("/callback")
async def oidc_callback(
    provider: str,
    code: str,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """
    OIDC callback handler.

    Placeholder — in production this exchanges the code for tokens,
    creates/finds the user, and issues a session JWT.
    """
    # TODO: Exchange code with provider, get user info
    # For now, return a placeholder response
    return {
        "status": "placeholder",
        "message": f"OIDC callback for {provider} received. Code exchange not yet implemented.",
        "code": code[:8] + "...",
    }


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------

@router.post("/refresh")
async def refresh_session(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Refresh the current JWT session by issuing a new token."""
    token = request.cookies.get("mc_session")
    if not token:
        raise HTTPException(status_code=401, detail="No active session")

    try:
        payload = decode_jwt(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    jti = payload.get("jti")
    if jti and await is_jwt_revoked(jti):
        raise HTTPException(status_code=401, detail="Session has been revoked")

    # Issue new JWT, revoke old one
    new_token, new_jti = create_jwt(
        user_id=uuid.UUID(payload["sub"]),
        org_ids=payload["org_ids"],
        active_org=payload["active_org"],
        role=payload["role"],
    )

    if jti:
        await revoke_jwt(jti)

    csrf = generate_csrf_token()
    _set_session_cookies(response, new_token, csrf)

    return {"message": "Session refreshed"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Invalidate the current session."""
    token = request.cookies.get("mc_session")
    if token:
        try:
            payload = decode_jwt(token)
            jti = payload.get("jti")
            if jti:
                await revoke_jwt(jti)
        except Exception:
            pass  # Token already invalid, just clear cookies

    response.delete_cookie("mc_session", path="/")
    response.delete_cookie("mc_csrf", path="/")
    return {"message": "Logged out"}
