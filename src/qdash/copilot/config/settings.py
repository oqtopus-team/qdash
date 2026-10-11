"""Copilot configuration loader.

This module loads Copilot settings from the YAML configuration files:
config.yaml (shared), chat.yaml (planner models and prompts) and
evaluation.yaml (the calibration evaluation model and scoring thresholds).

Uses ConfigLoader for unified configuration loading with local override support.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

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
    sampling_params: dict[str, Any] = Field(default_factory=dict)
    sampling_params_by_thinking_level: dict[str, dict[str, Any]] = Field(default_factory=dict)
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


class TaskChatConfig(BaseModel):
    """How a chat about one task result opens (figures, turns)."""

    enabled: bool = True
    multimodal: bool = True
    max_conversation_turns: int = 10
    max_expected_images: int | None = None


class CopilotConfig(BaseModel):
    """Copilot configuration."""

    enabled: bool = False
    response_language: str = "en"
    thinking_language: str = "en"
    model: ModelConfig = Field(default_factory=ModelConfig)
    # Selectable planner models for every chat, with or without a task result
    # as context. The first entry is the default; when unset, `model` is used.
    chat_models: list[ModelConfig] = Field(default_factory=list)
    # Models that judge calibration plots (evaluation.yaml). They are not
    # planners: the pi runtime declares them so pi-qcaleval can find the
    # calibration VLM; nothing in the API calls them directly.
    evaluation_models: list[ModelConfig] = Field(default_factory=list)
    # Backend serving the chat page and the analysis side panel: "pi" (Pi Agent
    # Runtime) or "litellm" (in-process).
    copilot_backend: str = "litellm"
    evaluation_metrics: EvaluationMetrics = Field(default_factory=EvaluationMetrics)
    scoring: dict[str, ScoringThreshold] = Field(default_factory=dict)
    system_prompt: str = ""
    initial_message: str = ""
    suggestions: list[Suggestion] = Field(default_factory=list)
    task_chat: TaskChatConfig = Field(default_factory=TaskChatConfig)


def select_chat_model(config: CopilotConfig, override: ModelConfig | None = None) -> ModelConfig:
    """The planner for a chat: a per-request override, else the first chat model, else `model`."""
    if override is not None:
        return override
    return config.chat_models[0] if config.chat_models else config.model


@lru_cache(maxsize=1)
def load_copilot_config() -> CopilotConfig:
    """Load Copilot configuration from YAML file.

    Uses ConfigLoader for unified loading with local override support.
    Configuration is loaded by merging copilot/config.yaml, copilot/chat.yaml,
    and copilot/evaluation.yaml, each with optional local overlays.

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
        # `analysis` was the key's name before task chats were called that.
        if "analysis" in data and "task_chat" not in data:
            data["task_chat"] = data.pop("analysis")
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
