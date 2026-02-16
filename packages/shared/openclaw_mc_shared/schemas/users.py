"""User management schemas (Phase 12)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, UUID4

from .common import Role


class UserType(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class UserAddRequest(BaseModel):
    """Add a user to the org (invite)."""
    type: UserType
    email: Optional[EmailStr] = None
    identifier: Optional[str] = None
    display_name: str = Field(min_length=1, max_length=200)
    role: Role = Role.CONTRIBUTOR


class UserUpdateRequest(BaseModel):
    """Update a user's role or display name."""
    role: Optional[Role] = None
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=200)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Single user response."""
    id: UUID4
    type: UserType
    email: Optional[str] = None
    identifier: Optional[str] = None
    display_name: str
    role: Role
    has_api_key: bool = False
    last_active: Optional[datetime] = None
    created_at: datetime


class UserAddResponse(BaseModel):
    """Response when adding a user. For agents, includes the one-time API key."""
    user: UserResponse
    api_key: Optional[str] = None  # Only present for agent users, shown ONCE


class UserListResponse(BaseModel):
    """List of users in an org."""
    data: List[UserResponse]


class ApiKeyRotateResponse(BaseModel):
    """Response after rotating an agent's API key."""
    api_key: str  # New plaintext key, shown ONCE
    previous_key_expires_at: datetime  # When the old key stops working
