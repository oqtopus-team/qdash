"""Unified configuration loader for QDash.

This module provides centralized YAML configuration loading with support for
local overrides. Each config file (e.g., settings.yaml) can have a corresponding
local override file (e.g., settings.local.yaml) that is merged on top.

Configuration files are loaded from:
- Docker: /app/config/
- Local development: config/ (relative to project root)

Local override files (*.local.yaml) are gitignored and allow per-developer
customization without modifying committed configuration files.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from qdash.common.paths import CONFIG_DIR


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence.

    Parameters
    ----------
    base : dict
        Base dictionary
    override : dict
        Override dictionary (values take precedence)

    Returns
    -------
    dict
        Merged dictionary

    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigLoader:
    """Unified configuration loader.

    Loads YAML configuration files with support for local overrides.
    Configuration files are automatically detected in either Docker
    or local development environments.

    Examples
    --------
    >>> config = ConfigLoader.load_settings()
    >>> ui_settings = config.get("ui", {})

    >>> metrics = ConfigLoader.load_metrics()
    >>> qubit_metrics = metrics.get("qubit_metrics", {})

    """

    # Container path (Docker environment) - imported from common.paths
    _CONFIG_DIR: Path = CONFIG_DIR
    # Local development path (relative to project root)
    LOCAL_CONFIG_DIR: Path = Path(__file__).parent.parent.parent.parent.parent / "config"

    @classmethod
    def get_config_dir(cls) -> Path:
        """Get the configuration directory.

        Returns
        -------
        Path
            The configuration directory path.
            Uses /app/config in Docker, or config/ in local development.

        """
        if cls._CONFIG_DIR.exists():
            return cls._CONFIG_DIR
        return cls.LOCAL_CONFIG_DIR

    @classmethod
    def _load_yaml(cls, path: Path) -> dict[str, Any]:
        """Load a YAML file.

        Parameters
        ----------
        path : Path
            Path to the YAML file

        Returns
        -------
        dict
            Parsed YAML content, or empty dict if file doesn't exist

        """
        if not path.exists():
            return {}
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @classmethod
    def _load_with_local(cls, filename: str) -> dict[str, Any]:
        """Load a YAML file with local override support.

        Parameters
        ----------
        filename : str
            Configuration filename (e.g., "settings.yaml")

        Returns
        -------
        dict
            Merged configuration from base file and local override

        """
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
        """Load settings configuration.

        Returns
        -------
        dict
            Settings from settings.yaml merged with settings.local.yaml

        """
        return cls._load_with_local("settings.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_metrics(cls) -> dict[str, Any]:
        """Load metrics configuration.

        Returns
        -------
        dict
            Metrics from metrics.yaml merged with metrics.local.yaml

        """
        return cls._load_with_local("metrics.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_copilot(cls) -> dict[str, Any]:
        """Load copilot configuration.

        Returns
        -------
        dict
            Copilot config from copilot.yaml merged with copilot.local.yaml

        """
        return cls._load_with_local("copilot.yaml")

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached configurations.

        Useful for testing or when configuration files change.
        """
        cls.load_settings.cache_clear()
        cls.load_metrics.cache_clear()
        cls.load_copilot.cache_clear()
