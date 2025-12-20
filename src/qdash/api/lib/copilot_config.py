"""Copilot configuration loader.

This module loads CopilotKit settings from YAML configuration file.
The configuration provides settings for the CopilotKit-powered metrics analysis assistant.

Uses ConfigLoader for unified configuration loading with local override support.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel
from qdash.api.lib.config_loader import ConfigLoader


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


class ModelConfig(BaseModel):
    """Model configuration for CopilotKit."""

    provider: str = "openai"
    name: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2048


class Suggestion(BaseModel):
    """Suggestion item for chat UI."""

    label: str
    prompt: str


class CopilotConfig(BaseModel):
    """Copilot configuration."""

    enabled: bool = False
    language: str = "en"
    model: ModelConfig = ModelConfig()
    evaluation_metrics: EvaluationMetrics = EvaluationMetrics()
    scoring: dict[str, ScoringThreshold] = {}
    system_prompt: str = ""
    initial_message: str = ""
    suggestions: list[Suggestion] = []


@lru_cache(maxsize=1)
def load_copilot_config() -> CopilotConfig:
    """Load Copilot configuration from YAML file.

    Uses ConfigLoader for unified loading with local override support.
    Configuration is loaded from copilot.yaml with optional copilot.local.yaml overlay.

    Returns
    -------
        CopilotConfig with all Copilot settings

    Notes
    -----
        Returns default config (disabled) if file not found

    """
    data = ConfigLoader.load_copilot()

    if not data:
        # Return default disabled config if file not found
        return CopilotConfig(enabled=False)

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
