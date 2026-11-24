"""Agent configuration loader.

Three YAML files merged by ConfigLoader: config.yaml (shared), chat.yaml
(planner models) and evaluation.yaml (the calibration evaluation model). The
last two come from config/agent/profiles/<name>/ when QDASH_AGENT_PROFILE
names a profile.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, model_validator

from qdash.common.config.loader import ConfigLoader

if TYPE_CHECKING:
    from collections.abc import Collection


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
    # "completion" for /v1/chat/completions only providers (e.g. DeepSeek). The
    # runtime treats any value other than "responses" as completion; a profile
    # accepts only these two (see qdash.common.config.agent_profile).
    api_style: str = "responses"


class TaskChatConfig(BaseModel):
    """How a chat about one task result opens."""

    multimodal: bool = True
    max_expected_images: int | None = None


class AgentConfig(BaseModel):
    """Agent configuration."""

    enabled: bool = False
    response_language: str = "en"
    thinking_language: str = "en"
    # Selectable planner models for every chat, with or without a task result
    # as context. The first entry is the default.
    chat_models: list[ModelConfig] = Field(default_factory=list)
    # Models that judge calibration plots (evaluation.yaml). They are not
    # planners: the selected entry is passed to pi-qcaleval for each run.
    evaluation_models: list[ModelConfig] = Field(default_factory=list)
    task_chat: TaskChatConfig = Field(default_factory=TaskChatConfig)
    # The default planner: `chat_models[0]`. Kept as a field so a per-request
    # override can be resolved into it (see select_chat_model).
    model: ModelConfig = Field(default_factory=ModelConfig)

    @model_validator(mode="after")
    def _default_model_is_the_first_chat_model(self) -> AgentConfig:
        if "model" not in self.model_fields_set and self.chat_models:
            self.model = self.chat_models[0]
        return self


class NoChatModelAvailableError(RuntimeError):
    """None of the configured chat models has its credential set in the agent runtime."""


def available_chat_models(
    config: AgentConfig, available: Collection[tuple[str, str]] | None
) -> list[ModelConfig]:
    """The chat models whose ``(provider, name)`` is in ``available``, in declared order.

    ``available`` comes from the agent runtime, which holds the model credentials;
    ``None`` means it could not be asked, and every configured model is kept.
    """
    if available is None:
        return list(config.chat_models)
    return [model for model in config.chat_models if (model.provider, model.name) in available]


def select_chat_model(
    config: AgentConfig,
    override: ModelConfig | None = None,
    available: Collection[tuple[str, str]] | None = None,
) -> ModelConfig:
    """The planner for a chat: a per-request override, else the first available chat model.

    Without ``available`` the first chat model is the default, as it always was. With it,
    the default is the first chat model in declared order whose credential is set, which
    is the model the chat menus label as the default.

    Raises
    ------
    NoChatModelAvailableError
        When no override is given and none of the chat models is available.

    """
    if override is not None:
        return override
    if not config.chat_models:
        return config.model
    models = available_chat_models(config, available)
    if not models:
        raise NoChatModelAvailableError(
            "No chat model is available: none of the models in chat_models has its API key "
            "set in the agent runtime. Set one in .env and recreate the agent-runtime container."
        )
    return models[0]


@lru_cache(maxsize=1)
def load_agent_config() -> AgentConfig:
    """Load the merged Agent configuration, or a disabled one when no file exists."""
    data = ConfigLoader.load_agent()
    if not data:
        return AgentConfig(enabled=False)
    try:
        # `analysis` was the key's name before task chats were called that.
        if "analysis" in data and "task_chat" not in data:
            data["task_chat"] = data.pop("analysis")
        # Keys of retired features are ignored rather than rejected.
        for retired in (
            "copilot_backend",  # legacy key name from the Copilot era
            "scoring",
            "evaluation_metrics",
            "system_prompt",
            "initial_message",
            "suggestions",
            "analysis_model",
            "analysis_models",
        ):
            data.pop(retired, None)
        return AgentConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid Agent configuration: {e}") from e


def clear_agent_config_cache() -> None:
    """Clear the cached Agent configuration (tests, config reload)."""
    load_agent_config.cache_clear()
