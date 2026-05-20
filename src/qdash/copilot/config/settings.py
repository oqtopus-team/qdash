"""Copilot configuration loader.

This module loads CopilotKit settings from YAML configuration file.
The configuration provides settings for the CopilotKit-powered metrics analysis assistant.

Uses ConfigLoader for unified configuration loading with local override support.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field

from qdash.common.config.loader import ConfigLoader


class ScoringThreshold(BaseModel):
    """Scoring threshold for a metric."""

    good: float
    excellent: float
    bad: float | None = None
    unit: str = ""
    higher_is_better: bool = True


class EvaluationMetrics(BaseModel):
    """Metrics to include in evaluation."""

    qubit: list[str] = Field(default_factory=list)
    coupling: list[str] = Field(default_factory=list)


class ModelConfig(BaseModel):
    """Model configuration for CopilotKit."""

    provider: str = "openai"
    name: str = "gpt-4.1"
    temperature: float | None = 0.7
    max_output_tokens: int = 16384
    base_url: str | None = None
    api_key_env: str | None = None
    keep_alive: str | None = None
    num_ctx: int | None = None
    top_p: float | None = None
    top_k: int | None = None
    reasoning_effort: str | None = None
    disable_thinking_instruction: bool = False
    # OpenAI-compatible servers vary in which endpoint they expose. Use
    # "responses" for the /v1/responses API (OpenAI, Ollama 0.13.3+) and
    # "chat_completions" for /v1/chat/completions only providers (e.g. DeepSeek).
    api_style: str = "responses"


class Suggestion(BaseModel):
    """Suggestion item for chat UI."""

    label: str
    prompt: str


class AnalysisConfig(BaseModel):
    """Task analysis configuration (side-panel chat in metrics modal)."""

    enabled: bool = True
    multimodal: bool = True
    max_conversation_turns: int = 10
    max_expected_images: int | None = None
    ai_review_max_expected_images: int | None = None
    ai_review_max_output_tokens: int | None = None
    ai_review_tasks: list[str] = Field(default_factory=list)
    ai_review_message: str = (
        "Review this completed calibration result and attach a concise operational review note."
    )


class CopilotConfig(BaseModel):
    """Copilot configuration."""

    enabled: bool = False
    response_language: str = "en"
    thinking_language: str = "en"
    model: ModelConfig = Field(default_factory=ModelConfig)
    # Optional override used only for task result analysis (image/chevron etc.).
    # When unset, `model` is used for both chat and analysis.
    analysis_model: ModelConfig | None = None
    # Optional list of selectable task result analysis models. The first entry
    # is used as the default when `analysis_model` is unset. `analysis_model`
    # remains for backward compatibility with existing copilot.yaml files.
    analysis_models: list[ModelConfig] = Field(default_factory=list)
    # Optional list of selectable models for general chat. The first entry is
    # used as the default. When unset, the configured `model` above is used.
    chat_models: list[ModelConfig] = Field(default_factory=list)
    evaluation_metrics: EvaluationMetrics = Field(default_factory=EvaluationMetrics)
    scoring: dict[str, ScoringThreshold] = Field(default_factory=dict)
    system_prompt: str = ""
    initial_message: str = ""
    suggestions: list[Suggestion] = Field(default_factory=list)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)


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
                scoring[key] = (
                    value if isinstance(value, ScoringThreshold) else ScoringThreshold(**value)
                )
            data["scoring"] = scoring

        return CopilotConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid Copilot configuration: {e}") from e


def clear_copilot_config_cache() -> None:
    """Clear the cached Copilot configuration.

    Useful for testing or when configuration needs to be reloaded.
    """
    load_copilot_config.cache_clear()
