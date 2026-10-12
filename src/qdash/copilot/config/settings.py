"""Copilot configuration loader.

Three YAML files, each with an optional `*.local.yaml` overlay, merged by
ConfigLoader: config.yaml (shared), chat.yaml (planner models) and
evaluation.yaml (the calibration evaluation model).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field, model_validator

from qdash.common.config.loader import ConfigLoader


class ModelConfig(BaseModel):
    """One model as the Pi Agent Runtime declares it."""

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


class TaskChatConfig(BaseModel):
    """How a chat about one task result opens."""

    multimodal: bool = True
    max_expected_images: int | None = None


class CopilotConfig(BaseModel):
    """Copilot configuration."""

    enabled: bool = False
    response_language: str = "en"
    thinking_language: str = "en"
    # Selectable planner models for every chat, with or without a task result
    # as context. The first entry is the default.
    chat_models: list[ModelConfig] = Field(default_factory=list)
    # Models that judge calibration plots (evaluation.yaml). They are not
    # planners: the pi runtime declares them so pi-qcaleval can find the
    # calibration VLM; nothing in the API calls them directly.
    evaluation_models: list[ModelConfig] = Field(default_factory=list)
    task_chat: TaskChatConfig = Field(default_factory=TaskChatConfig)
    # The default planner: `chat_models[0]`. Kept as a field so a per-request
    # override can be resolved into it (see select_chat_model).
    model: ModelConfig = Field(default_factory=ModelConfig)

    @model_validator(mode="after")
    def _default_model_is_the_first_chat_model(self) -> CopilotConfig:
        if "model" not in self.model_fields_set and self.chat_models:
            self.model = self.chat_models[0]
        return self


def select_chat_model(config: CopilotConfig, override: ModelConfig | None = None) -> ModelConfig:
    """The planner for a chat: a per-request override, else the first chat model."""
    if override is not None:
        return override
    return config.chat_models[0] if config.chat_models else config.model


@lru_cache(maxsize=1)
def load_copilot_config() -> CopilotConfig:
    """Load the merged Copilot configuration, or a disabled one when no file exists."""
    data = ConfigLoader.load_copilot()
    if not data:
        return CopilotConfig(enabled=False)
    try:
        # `analysis` was the key's name before task chats were called that.
        if "analysis" in data and "task_chat" not in data:
            data["task_chat"] = data.pop("analysis")
        # Keys of retired features are ignored rather than rejected.
        for retired in (
            "copilot_backend",
            "scoring",
            "evaluation_metrics",
            "system_prompt",
            "initial_message",
            "suggestions",
            "analysis_model",
            "analysis_models",
        ):
            data.pop(retired, None)
        return CopilotConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid Copilot configuration: {e}") from e


def clear_copilot_config_cache() -> None:
    """Clear the cached Copilot configuration (tests, config reload)."""
    load_copilot_config.cache_clear()
