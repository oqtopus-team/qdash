"""Unified configuration API router.

This module provides a single endpoint to fetch all application configuration,
enabling the frontend to initialize with a single API call.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from qdash.api.lib.config_loader import ConfigLoader

router = APIRouter(tags=["config"])


class UITaskFilesSettings(BaseModel):
    """Task files editor settings."""

    default_backend: str | None = None
    default_view_mode: str | None = None
    sort_order: str | None = None


class UISettings(BaseModel):
    """UI-specific settings."""

    task_files: UITaskFilesSettings = Field(default_factory=UITaskFilesSettings)


class AllConfigResponse(BaseModel):
    """Response containing all application configuration."""

    ui: UISettings = Field(default_factory=UISettings)
    metrics: dict[str, Any] = Field(default_factory=dict)
    copilot: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/config/all",
    response_model=AllConfigResponse,
    summary="Get all configuration",
    description="Fetch all application configuration in a single request",
    operation_id="getConfigAll",
)
def get_config_all() -> AllConfigResponse:
    """Get all application configuration.

    This endpoint returns all configuration needed by the frontend in a single
    request, including UI settings, metrics configuration, and copilot settings.

    Configuration is loaded from YAML files with support for local overrides:
    - settings.yaml + settings.local.yaml
    - metrics.yaml + metrics.local.yaml
    - copilot.yaml + copilot.local.yaml

    Returns
    -------
    AllConfigResponse
        All application configuration

    """
    settings = ConfigLoader.load_settings()
    metrics = ConfigLoader.load_metrics()
    copilot = ConfigLoader.load_copilot()

    # Extract UI settings
    ui_config = settings.get("ui", {})
    task_files = ui_config.get("task_files", {})

    return AllConfigResponse(
        ui=UISettings(
            task_files=UITaskFilesSettings(
                default_backend=task_files.get("default_backend"),
                default_view_mode=task_files.get("default_view_mode"),
                sort_order=task_files.get("sort_order"),
            )
        ),
        metrics=metrics,
        copilot=copilot,
    )
