"""Tests for configuration loading."""

import tempfile
from pathlib import Path

import pytest
import yaml

from mc_bridge.config import BridgeConfig, load_config


def test_load_config_from_yaml(tmp_path):
    config_data = {
        "mission_control": {"url": "https://mc.example.com"},
        "agents": [
            {"name": "agent-1", "api_key_env": "KEY_1", "org_slug": "acme"}
        ],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config_data))

    cfg = load_config(path)
    assert cfg.mission_control.url == "https://mc.example.com"
    assert len(cfg.agents) == 1
    assert cfg.agents[0].name == "agent-1"
    assert cfg.agents[0].org_slug == "acme"


def test_load_config_defaults():
    cfg = BridgeConfig()
    assert cfg.mission_control.url == "http://localhost:8000"
    assert cfg.state.db_path == "./data/bridge_state.db"
    assert cfg.metrics.port == 9090


def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path.yaml")
