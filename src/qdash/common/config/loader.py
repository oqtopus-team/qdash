"""Unified configuration loader for QDash."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from qdash.common.config.agent_profile import (
    load_agent_profile_file,
    resolve_agent_config_path,
    resolve_agent_model_files,
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
    def get_agent_config_path(cls) -> Path:
        """The shared Agent ``config.yaml`` (see ``resolve_agent_config_path``)."""
        return resolve_agent_config_path(cls.get_config_dir())

    @classmethod
    @lru_cache(maxsize=1)
    def load_agent(cls) -> dict[str, Any]:
        """Load agent configuration.

        ``config.yaml`` is shared: ``config/agent/config.yaml``, or the file
        that ``AGENT_CONFIG_PATH`` names. The chat and evaluation models come
        from ``chat.yaml`` and ``evaluation.yaml`` next to it, or from the
        profile that ``QDASH_AGENT_PROFILE`` names (see ``agent_profile``).
        The variables are read on every uncached load, so ``clear_cache``
        picks up the current selection.
        """
        config_path = cls.get_agent_config_path()
        if not config_path.is_file():
            logger.warning("Agent config %s not found; using defaults", config_path)
        config = cls._load_yaml(config_path)
        files = resolve_agent_model_files(config_path)
        if files.profile is None:
            for path in (files.chat, files.evaluation):
                config = _deep_merge(config, cls._load_yaml(path))
            return config
        logger.info("Agent profile %s: %s", files.profile, files.chat.parent)
        config = _deep_merge(config, load_agent_profile_file("chat", files.chat))
        return _deep_merge(config, load_agent_profile_file("evaluation", files.evaluation))

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
        cls.load_agent.cache_clear()
        cls.load_backend.cache_clear()
        cls.load_workflow.cache_clear()
