"""Backend configuration loader.

This module re-exports from qdash.common.backend_config for backward compatibility.
New code should import directly from qdash.common.backend_config.
"""

# Re-export from common for backward compatibility
from qdash.common.backend_config import (
    BackendConfig,
    BackendDefinition,
    clear_cache,
    get_available_backends,
    get_default_backend,
    get_task_category,
    get_tasks,
    is_task_available,
    load_backend_config,
)

__all__ = [
    "BackendConfig",
    "BackendDefinition",
    "clear_cache",
    "get_available_backends",
    "get_default_backend",
    "get_task_category",
    "get_tasks",
    "is_task_available",
    "load_backend_config",
]
