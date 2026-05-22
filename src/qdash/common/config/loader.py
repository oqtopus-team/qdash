"""Unified configuration loader for QDash."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from qdash.common.config.paths import CONFIG_DIR


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigLoader:
    """Unified configuration loader with local override support."""

    _CONFIG_DIR: Path = CONFIG_DIR
    LOCAL_CONFIG_DIR: Path = Path(__file__).resolve().parents[4] / "config"

    @classmethod
    def get_config_dir(cls) -> Path:
        """Get the configuration directory."""
        if cls._CONFIG_DIR.exists():
            return cls._CONFIG_DIR
        return cls.LOCAL_CONFIG_DIR

    @classmethod
    def _load_yaml(cls, path: Path) -> dict[str, Any]:
        """Load a YAML file."""
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @classmethod
    def _load_with_local(cls, filename: str) -> dict[str, Any]:
        """Load a YAML file with local override support."""
        config_dir = cls.get_config_dir()
        base_path = config_dir / filename
        local_path = config_dir / filename.replace(".yaml", ".local.yaml")

        config = cls._load_yaml(base_path)
        if local_path.exists():
            local_config = cls._load_yaml(local_path)
            config = _deep_merge(config, local_config)
        return config

    @classmethod
    @lru_cache(maxsize=1)
    def load_settings(cls) -> dict[str, Any]:
        """Load settings configuration."""
        return cls._load_with_local("settings.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_metrics(cls) -> dict[str, Any]:
        """Load metrics configuration."""
        return cls._load_with_local("metrics.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_copilot(cls) -> dict[str, Any]:
        """Load copilot configuration."""
        return cls._load_with_local("copilot.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_backend(cls) -> dict[str, Any]:
        """Load backend configuration."""
        return cls._load_with_local("backend.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_workflow(cls) -> dict[str, Any]:
        """Load workflow configuration.

        Workflow settings used to live under ``settings.yaml``. Keep that path
        as a fallback so local overrides continue to work during migration.
        """
        workflow_config = cls._load_with_local("workflow.yaml")
        if workflow_config:
            return workflow_config

        settings = cls.load_settings()
        workflow_settings = settings.get("workflow", {})
        return workflow_settings if isinstance(workflow_settings, dict) else {}

    @classmethod
    def load_policy(cls) -> dict[str, Any]:
        """Load provenance policy configuration."""
        return cls._load_with_local("policy.yaml")

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached configurations."""
        cls.load_settings.cache_clear()
        cls.load_metrics.cache_clear()
        cls.load_copilot.cache_clear()
        cls.load_backend.cache_clear()
        cls.load_workflow.cache_clear()
