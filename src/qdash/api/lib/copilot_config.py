"""Copilot configuration loader.

This module loads CopilotKit settings from YAML configuration file.
The configuration provides settings for the CopilotKit-powered metrics analysis assistant.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class ScoringThreshold(BaseModel):
    """Scoring threshold for a metric."""

    good: float
    excellent: float
    unit: str = ""
    higher_is_better: bool = True


class EvaluationMetrics(BaseModel):
    """Metrics to include in evaluation."""

    qubit: list[str] = []
    coupling: list[str] = []


class CopilotConfig(BaseModel):
    """Copilot configuration."""

    enabled: bool = False
    evaluation_metrics: EvaluationMetrics = EvaluationMetrics()
    scoring: dict[str, ScoringThreshold] = {}
    system_prompt: str = ""
    initial_message: str = ""


@lru_cache(maxsize=1)
def load_copilot_config() -> CopilotConfig:
    """Load Copilot configuration from YAML file.

    Returns
    -------
        CopilotConfig with all Copilot settings

    Notes
    -----
        Returns default config (disabled) if file not found

    """
    # Try multiple possible locations for the config file
    possible_paths = [
        # Docker environment: mounted at /app/config
        Path("/app/config/copilot.yaml"),
        # Local development: relative to project root
        Path(__file__).parent.parent.parent.parent.parent / "config" / "copilot.yaml",
        # Environment variable override
        Path(os.getenv("COPILOT_CONFIG_PATH", "")) if os.getenv("COPILOT_CONFIG_PATH") else None,
    ]

    config_path = None
    for path in possible_paths:
        if path and path.exists():
            config_path = path
            break

    if not config_path:
        # Return default disabled config if file not found
        return CopilotConfig(enabled=False)

    with open(config_path) as f:
        data = yaml.safe_load(f)

    try:
        # Transform scoring dict to use ScoringThreshold models
        if "scoring" in data:
            scoring = {}
            for key, value in data["scoring"].items():
                scoring[key] = ScoringThreshold(**value)
            data["scoring"] = scoring

        return CopilotConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid Copilot configuration: {e}") from e


def clear_copilot_config_cache() -> None:
    """Clear the cached Copilot configuration.

    Useful for testing or when configuration needs to be reloaded.
    """
    load_copilot_config.cache_clear()
