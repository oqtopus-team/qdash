"""Backend configuration loader.

This module loads backend configuration from YAML configuration file.
The configuration defines available backends and their tasks.

Uses ConfigLoader for unified configuration loading with local override support.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field
from qdash.common.config_loader import ConfigLoader


class BackendDefinition(BaseModel):
    """Definition of a single backend."""

    description: str = ""
    tasks: list[str] = Field(default_factory=list)


class BackendConfig(BaseModel):
    """Complete backend configuration."""

    default_backend: str = "qubex"
    backends: dict[str, BackendDefinition] = Field(default_factory=dict)
    categories: dict[str, list[str]] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def load_backend_config() -> BackendConfig:
    """Load backend configuration from YAML file.

    Uses ConfigLoader for unified loading with local override support.
    Configuration is loaded from backend.yaml with optional backend.local.yaml overlay.

    Returns
    -------
    BackendConfig
        Backend configuration with all definitions

    Raises
    ------
    ValueError
        If config file is invalid

    """
    data = ConfigLoader.load_backend()

    try:
        return BackendConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid backend configuration: {e}") from e


def get_tasks(backend: str) -> list[str]:
    """Get list of tasks for a backend.

    Parameters
    ----------
    backend : str
        Backend name (e.g., 'qubex', 'fake')

    Returns
    -------
    list[str]
        List of task names for this backend.
        Returns empty list if backend not found.

    """
    config = load_backend_config()
    backend_def = config.backends.get(backend)
    if backend_def is None:
        return []
    return backend_def.tasks


def get_available_backends() -> list[str]:
    """Get list of available backend names.

    Returns
    -------
    list[str]
        List of backend names defined in configuration

    """
    config = load_backend_config()
    return list(config.backends.keys())


def get_default_backend() -> str:
    """Get the default backend name.

    Environment variable DEFAULT_BACKEND takes precedence over config file.

    Returns
    -------
    str
        Default backend name from environment variable or configuration

    """
    env_backend = os.environ.get("DEFAULT_BACKEND")
    if env_backend:
        return env_backend
    config = load_backend_config()
    return config.default_backend


def is_task_available(task_name: str, backend: str) -> bool:
    """Check if a task is available for a backend.

    Parameters
    ----------
    task_name : str
        Task name
    backend : str
        Backend name

    Returns
    -------
    bool
        True if task is listed for this backend

    """
    tasks = get_tasks(backend)
    return task_name in tasks


def get_task_category(task_name: str) -> str | None:
    """Get the category for a task.

    Parameters
    ----------
    task_name : str
        Task name

    Returns
    -------
    str | None
        Category name, or None if task not in any category

    """
    config = load_backend_config()
    for category, tasks in config.categories.items():
        if task_name in tasks:
            return category
    return None


def clear_cache() -> None:
    """Clear the configuration cache.

    Useful for testing or when configuration files change.
    """
    load_backend_config.cache_clear()
    ConfigLoader.clear_cache()
