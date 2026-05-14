"""Backend configuration loader."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field

from qdash.common.config.loader import ConfigLoader


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
    """Load backend configuration from YAML file."""
    data = ConfigLoader.load_backend()
    try:
        return BackendConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid backend configuration: {e}") from e


def get_tasks(backend: str) -> list[str]:
    """Get list of tasks for a backend."""
    config = load_backend_config()
    backend_def = config.backends.get(backend)
    if backend_def is None:
        return []
    return backend_def.tasks


def get_available_backends() -> list[str]:
    """Get list of available backend names."""
    return list(load_backend_config().backends.keys())


def get_default_backend() -> str:
    """Get the default backend name."""
    env_backend = os.environ.get("DEFAULT_BACKEND")
    if env_backend:
        return env_backend
    return load_backend_config().default_backend


def is_task_available(task_name: str, backend: str) -> bool:
    """Check if a task is available for a backend."""
    return task_name in get_tasks(backend)


def get_task_category(task_name: str) -> str | None:
    """Get the category for a task."""
    config = load_backend_config()
    for category, tasks in config.categories.items():
        if task_name in tasks:
            return category
    return None


def clear_cache() -> None:
    """Clear the configuration cache."""
    load_backend_config.cache_clear()
    ConfigLoader.clear_cache()
