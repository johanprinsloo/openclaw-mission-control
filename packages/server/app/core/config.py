"""
Application configuration loaded from environment variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Mission Control server configuration."""

    model_config = SettingsConfigDict(env_prefix="MC_", env_file=".env", extra="ignore")

    # Deployment mode
    deployment_mode: Literal["single-tenant", "multi-tenant"] = "single-tenant"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mission_control"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # OIDC (GitHub)
    github_client_id: str = ""
    github_client_secret: str = ""

    # OIDC (Google)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
