"""
Organization-related Pydantic schemas shared between server and bridge.

Covers: Org CRUD request/response, OrgSettings and all sub-models,
org lifecycle states.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OrgStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_DELETION = "pending_deletion"
    DELETED = "deleted"


class OidcProvider(str, Enum):
    GITHUB = "github"
    GOOGLE = "google"


class EvidenceType(str, Enum):
    PR_LINK = "pr_link"
    TEST_RESULTS = "test_results"
    DOC_URL = "doc_url"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    SIGNAL = "signal"


# ---------------------------------------------------------------------------
# Org Settings sub-models
# ---------------------------------------------------------------------------

class AuthenticationSettings(BaseModel):
    allowed_oidc_providers: list[OidcProvider] = Field(
        default=[OidcProvider.GITHUB, OidcProvider.GOOGLE],
        description="OIDC providers enabled for human login",
    )
    api_key_rotation_reminder_days: int = Field(
        default=90,
        ge=0,
        description="Days before API key expiry to remind admins (0 = disabled)",
    )


class TaskDefaultsSettings(BaseModel):
    default_required_evidence_types: list[EvidenceType] = Field(
        default=[],
        description="Evidence types required by default for new tasks",
    )
    default_priority: str = Field(
        default="medium",
        pattern=r"^(low|medium|high|critical)$",
        description="Default priority for new tasks",
    )


class NotificationSettings(BaseModel):
    enabled_channels: list[NotificationChannel] = Field(
        default=[NotificationChannel.EMAIL],
        description="External notification channels available to users",
    )
    default_channel: Optional[NotificationChannel] = Field(
        default=NotificationChannel.EMAIL,
        description="Default notification channel for new users",
    )
    email_from_address: Optional[str] = Field(
        default=None,
        description="From address for outbound emails (if email enabled)",
    )


class GitHubIntegration(BaseModel):
    enabled: bool = False
    org_name: Optional[str] = Field(default=None, description="GitHub organization name")


class GoogleWorkspaceIntegration(BaseModel):
    enabled: bool = False
    domain: Optional[str] = Field(default=None, description="Google Workspace domain")


class IntegrationsSettings(BaseModel):
    github: GitHubIntegration = Field(default_factory=GitHubIntegration)
    google_workspace: GoogleWorkspaceIntegration = Field(
        default_factory=GoogleWorkspaceIntegration
    )


class AgentLimitsSettings(BaseModel):
    max_concurrent_sub_agents: Optional[int] = Field(
        default=None,
        ge=1,
        description="Maximum concurrent sub-agents (null = unlimited)",
    )
    allowed_models: list[str] = Field(
        default=[],
        description="Models allowed for sub-agents (empty = all models allowed)",
    )
    sub_agent_default_timeout_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="Default timeout for sub-agents in minutes",
    )


class BackupSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable scheduled backups")
    schedule_cron: Optional[str] = Field(
        default="0 2 * * *",
        description="Cron expression for backup schedule",
    )
    destination: Optional[str] = Field(
        default=None,
        description="Backup destination (S3 URI or local path)",
    )
    retention_days: int = Field(
        default=30,
        ge=1,
        description="Days to retain backups",
    )


class OrgSettings(BaseModel):
    """Complete org-level settings schema. All fields optional with defaults."""

    authentication: AuthenticationSettings = Field(
        default_factory=AuthenticationSettings
    )
    task_defaults: TaskDefaultsSettings = Field(default_factory=TaskDefaultsSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    integrations: IntegrationsSettings = Field(default_factory=IntegrationsSettings)
    agent_limits: AgentLimitsSettings = Field(default_factory=AgentLimitsSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    deletion_grace_period_days: int = Field(
        default=30,
        ge=7,
        le=90,
        description="Days before org deletion is finalized",
    )


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

# Valid state transitions for org lifecycle
ORG_TRANSITIONS: dict[OrgStatus, list[OrgStatus]] = {
    OrgStatus.ACTIVE: [OrgStatus.SUSPENDED, OrgStatus.PENDING_DELETION],
    OrgStatus.SUSPENDED: [OrgStatus.ACTIVE, OrgStatus.PENDING_DELETION],
    OrgStatus.PENDING_DELETION: [OrgStatus.ACTIVE, OrgStatus.DELETED],
    OrgStatus.DELETED: [],
}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Organization display name")
    slug: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
        description="URL-safe org identifier",
    )


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    settings: Optional[dict] = Field(
        None,
        description="Partial settings update (deep-merged via JSON Merge Patch)",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class OrgResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: OrgStatus
    settings: OrgSettings
    created_at: datetime
    updated_at: datetime
    deletion_scheduled_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OrgListItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: OrgStatus
    role: str  # the requesting user's role in this org

    model_config = {"from_attributes": True}


class OrgListResponse(BaseModel):
    data: list[OrgListItem]
