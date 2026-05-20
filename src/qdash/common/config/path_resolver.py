"""Helpers for resolving runtime file paths across host and container modes."""

from __future__ import annotations

import os
from pathlib import Path

from qdash.common.config.paths import (
    CALIB_DATA_BASE,
    CALIBTASKS_DIR,
    QUBEX_CONFIG_BASE,
    SERVICE_DIR,
    TEMPLATES_DIR,
    USER_FLOWS_DIR,
)

REPO_WORKFLOW_DIR = Path("src/qdash/workflow")
REPO_QUBEX_CONFIG_BASE = Path("config/qubex-config")


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else None


def _resolve_runtime_base_path(
    *,
    env_name: str | None,
    container_path: Path,
    repo_local_path: Path | None = None,
) -> Path:
    """Resolve a base path with explicit env, container, then repo-local fallback."""
    if env_name:
        env_value = _env_path(env_name)
        if env_value is not None and env_value.exists():
            return env_value
    if container_path.exists():
        return container_path
    if repo_local_path is not None:
        return repo_local_path.resolve()
    return container_path


def resolve_config_base_path() -> Path:
    """Resolve the Qubex config directory for host and container execution."""
    return _resolve_runtime_base_path(
        env_name="CONFIG_PATH",
        container_path=QUBEX_CONFIG_BASE,
        repo_local_path=REPO_QUBEX_CONFIG_BASE,
    )


def resolve_calibtasks_base_path() -> Path:
    """Resolve the calibration task directory for host and container execution."""
    return _resolve_runtime_base_path(
        env_name="CALTASKS_PATH",
        container_path=CALIBTASKS_DIR,
        repo_local_path=REPO_WORKFLOW_DIR / "calibtasks",
    )


def resolve_workflow_path(container_path: Path, relative_path: str) -> Path:
    """Resolve a workflow path for host and container execution."""
    return _resolve_runtime_base_path(
        env_name=None,
        container_path=container_path,
        repo_local_path=REPO_WORKFLOW_DIR / relative_path,
    )


def resolve_workflow_templates_dir() -> Path:
    """Resolve the workflow templates directory."""
    return resolve_workflow_path(TEMPLATES_DIR, "templates")


def resolve_workflow_service_dir() -> Path:
    """Resolve the workflow service helpers directory."""
    return resolve_workflow_path(SERVICE_DIR, "service")


def resolve_user_flows_dir() -> Path:
    """Resolve the user flows directory used by the current runtime."""
    return resolve_workflow_path(USER_FLOWS_DIR, "user_flows")


def to_container_user_flow_path(file_path: Path, *, runtime_user_flows_dir: Path) -> Path:
    """Map a runtime-local user flow path to the deployment service container path."""
    try:
        return USER_FLOWS_DIR / file_path.relative_to(runtime_user_flows_dir)
    except ValueError:
        return file_path


def resolve_calib_data_path(path: str | Path) -> Path:
    """Resolve a calibration data path stored from either host or container runtime.

    Workflow workers commonly store figure paths using the container mount point
    (``/app/calib_data``). When the API runs directly on the host for local
    development, those paths need to be read through ``CALIB_DATA_PATH`` instead.
    """
    candidate = Path(path)
    if candidate.exists():
        return candidate

    try:
        relative_path = candidate.relative_to(CALIB_DATA_BASE)
    except ValueError:
        return candidate

    local_base = Path(os.getenv("CALIB_DATA_PATH", "calib_data")).expanduser()
    mapped = local_base / relative_path
    return mapped if mapped.exists() else candidate
