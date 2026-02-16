"""
Configuration loading and validation.

Loads bridge configuration from YAML file with environment variable resolution
for secrets (API keys are never stored in config files).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class MissionControlConfig(BaseModel):
    url: str = "http://localhost:8000"
    verify_tls: bool = True
    request_timeout_seconds: int = 30
    sse_heartbeat_interval_seconds: int = 30
    sse_heartbeat_timeout_seconds: int = 90


class GatewayConfig(BaseModel):
    url: str = "http://localhost:8080"
    api_key_env: str = "OPENCLAW_GATEWAY_KEY"

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class AgentConfig(BaseModel):
    name: str
    api_key_env: str
    org_slug: str
    auto_subscribe: bool = True
    history_fetch_count: int = 50

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


class StateConfig(BaseModel):
    db_path: str = "./data/bridge_state.db"


class LoggingConfig(BaseModel):
    level: str = "info"
    format: Literal["json", "text"] = "json"


class MetricsConfig(BaseModel):
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 9090


class BridgeConfig(BaseModel):
    mission_control: MissionControlConfig = Field(default_factory=MissionControlConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    agents: list[AgentConfig] = Field(default_factory=list)
    state: StateConfig = Field(default_factory=StateConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)


def load_config(path: str | Path) -> BridgeConfig:
    """Load and validate bridge configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return BridgeConfig.model_validate(raw)
