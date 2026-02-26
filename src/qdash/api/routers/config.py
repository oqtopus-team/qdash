"""Unified configuration API router.

This module provides a single endpoint to fetch all application configuration,
enabling the frontend to initialize with a single API call.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from qdash.api.dependencies import get_config_service  # noqa: TCH002
from qdash.api.services.config_service import ConfigService  # noqa: TCH002

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
def get_config_all(
    service: Annotated[ConfigService, Depends(get_config_service)],
) -> AllConfigResponse:
    """Get all application configuration.

    This endpoint returns all configuration needed by the frontend in a single
    request, including UI settings, metrics configuration, and copilot settings.

    Returns
    -------
    AllConfigResponse
        All application configuration

    """
    config = service.get_all_config()
    ui = config["ui"]
    task_files = ui["task_files"]

    return AllConfigResponse(
        ui=UISettings(
            task_files=UITaskFilesSettings(
                default_backend=task_files.get("default_backend"),
                default_view_mode=task_files.get("default_view_mode"),
                sort_order=task_files.get("sort_order"),
            )
        ),
        metrics=config["metrics"],
        copilot=config["copilot"],
    )
