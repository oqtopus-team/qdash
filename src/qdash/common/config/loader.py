"""Unified configuration loader for QDash."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from qdash.common.config.copilot_profile import (
    copilot_profile_files,
    load_copilot_profile_file,
    selected_copilot_profile,
)
from qdash.common.config.paths import CONFIG_DIR

logger = logging.getLogger(__name__)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _expand_env_vars(value: Any) -> Any:
    """Expand environment variable references in loaded YAML values."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env_vars(item) for key, item in value.items()}
    return value


class ConfigLoader:
    """Unified configuration loader."""

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
            config = yaml.safe_load(f) or {}
        expanded = _expand_env_vars(config)
        return expanded if isinstance(expanded, dict) else {}

    @classmethod
    def _load_config(cls, filename: str) -> dict[str, Any]:
        """Load a YAML file relative to the configuration directory."""
        return cls._load_yaml(cls.get_config_dir() / filename)

    @classmethod
    @lru_cache(maxsize=1)
    def load_settings(cls) -> dict[str, Any]:
        """Load settings configuration."""
        return cls._load_config("app/settings.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_metrics(cls) -> dict[str, Any]:
        """Load metrics configuration."""
        return cls._load_config("domain/metrics.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_copilot(cls) -> dict[str, Any]:
        """Load copilot configuration.

        ``config.yaml`` is shared. The chat and evaluation models come from
        ``chat.yaml`` and ``evaluation.yaml``, or from the profile that
        ``QDASH_COPILOT_PROFILE`` names (see ``copilot_profile``). The
        variable is read on every uncached load, so ``clear_cache`` picks up
        the current selection.
        """
        config = cls._load_config("copilot/config.yaml")
        profile = selected_copilot_profile()
        if profile is None:
            for filename in ("copilot/chat.yaml", "copilot/evaluation.yaml"):
                config = _deep_merge(config, cls._load_config(filename))
            return config
        files = copilot_profile_files(cls.get_config_dir() / "copilot", profile)
        logger.info("Copilot profile %s: %s", profile, files["chat"].parent)
        for kind, path in files.items():
            config = _deep_merge(config, load_copilot_profile_file(kind, path))
        return config

    @classmethod
    @lru_cache(maxsize=1)
    def load_backend(cls) -> dict[str, Any]:
        """Load backend configuration."""
        return cls._load_config("app/backend.yaml")

    @classmethod
    @lru_cache(maxsize=1)
    def load_workflow(cls) -> dict[str, Any]:
        """Load workflow configuration."""
        return cls._load_config("app/workflow.yaml")

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached configurations."""
        cls.load_settings.cache_clear()
        cls.load_metrics.cache_clear()
        cls.load_copilot.cache_clear()
        cls.load_backend.cache_clear()
        cls.load_workflow.cache_clear()
