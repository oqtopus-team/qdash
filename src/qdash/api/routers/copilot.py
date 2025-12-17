"""Copilot API router for AI assistant configuration.

This router provides public endpoints for copilot configuration
that do not require authentication.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from qdash.api.lib.copilot_config import load_copilot_config

router = APIRouter()


@router.get(
    "/config",
    summary="Get Copilot configuration",
    operation_id="getCopilotConfig",
)
async def get_copilot_config() -> dict[str, Any]:
    """Get Copilot configuration for the metrics assistant.

    Retrieves the Copilot configuration from YAML, including:
    - enabled: Whether Copilot is enabled
    - evaluation_metrics: Which metrics to use for multi-metric evaluation
    - scoring: Thresholds for good/excellent ratings per metric
    - system_prompt: The AI assistant's system prompt
    - initial_message: The initial greeting message

    Returns
    -------
    dict[str, Any]
        Copilot configuration dictionary

    """
    config = load_copilot_config()
    return config.model_dump()
