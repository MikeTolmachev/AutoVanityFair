import os
import tempfile

import pytest
import yaml

from src.core.config_manager import ConfigManager, _resolve_env_vars, _resolve_dict, AppConfig


def test_resolve_env_vars():
    os.environ["TEST_VAR_ABC"] = "hello"
    result = _resolve_env_vars("prefix_${TEST_VAR_ABC}_suffix")
    assert result == "prefix_hello_suffix"
    del os.environ["TEST_VAR_ABC"]


def test_resolve_env_vars_missing():
    result = _resolve_env_vars("${NONEXISTENT_VAR_XYZ}")
    assert result == ""


def test_resolve_dict():
    os.environ["MY_KEY"] = "secret"
    d = {"key": "${MY_KEY}", "nested": {"inner": "${MY_KEY}"}, "plain": "no_var"}
    resolved = _resolve_dict(d)
    assert resolved["key"] == "secret"
    assert resolved["nested"]["inner"] == "secret"
    assert resolved["plain"] == "no_var"
    del os.environ["MY_KEY"]


def test_app_config_defaults():
    config = AppConfig()
    assert config.ai.provider == "openai"
    assert config.scheduling.timezone == "Europe/Berlin"
    assert config.safety.hourly_action_limit == 8


def test_config_manager_loads_yaml(tmp_path):
    config_data = {
        "ai": {"provider": "anthropic"},
        "scheduling": {"timezone": "UTC"},
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    cm = ConfigManager(config_path=str(config_file), env_file=None)
    assert cm.ai.provider == "anthropic"
    assert cm.scheduling.timezone == "UTC"


def test_config_manager_env_resolution(tmp_path):
    os.environ["TEST_API_KEY"] = "sk-test123"
    config_data = {
        "ai": {
            "provider": "openai",
            "openai": {"api_key": "${TEST_API_KEY}"},
        }
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    cm = ConfigManager(config_path=str(config_file), env_file=None)
    assert cm.ai.openai.api_key == "sk-test123"
    del os.environ["TEST_API_KEY"]
