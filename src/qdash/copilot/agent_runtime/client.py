"""LLM client and request construction helpers for Copilot agents."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qdash.copilot.config import CopilotConfig


def build_litellm_kwargs(config: CopilotConfig) -> dict[str, Any]:
    """Build provider-aware LiteLLM SDK kwargs from Copilot model configuration."""
    model = config.model
    provider = model.provider.lower()
    configured_name = resolve_model_config_value(model.name, field_name="model") or model.name
    if provider == "ollama" and not configured_name.startswith("ollama_chat/"):
        model_name = f"ollama_chat/{configured_name}"
    elif provider == "vllm" and "/" not in configured_name:
        model_name = f"hosted_vllm/{configured_name}"
    elif configured_name.startswith(f"{provider}/"):
        model_name = configured_name
    elif provider in {"bedrock", "openai", "anthropic"}:
        model_name = f"{provider}/{configured_name}"
    else:
        model_name = configured_name
    kwargs: dict[str, Any] = {"model": model_name}

    if provider == "bedrock":
        aws_region_name = os.environ.get("AWS_REGION")
        api_base = os.environ.get("AWS_BASE_URL")
        kwargs["api_base"] = api_base.rstrip("/")
        kwargs["aws_region_name"] = aws_region_name

        bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
        if not bearer_token:
            raise ValueError(
                "Bedrock API key environment variable is not set: AWS_BEARER_TOKEN_BEDROCK"
            )
        kwargs["api_key"] = bearer_token
        kwargs["aws_access_key_id"] = "bedrock-api-key"
        kwargs["aws_secret_access_key"] = "bedrock-api-key"
        return kwargs

    base_url = resolve_model_config_value(model.base_url, field_name="base_url")
    if base_url:
        kwargs["api_base"] = base_url.rstrip("/")

    if model.api_key_env:
        kwargs["api_key"] = os.environ.get(model.api_key_env, "")

    return kwargs


def normalize_openai_compatible_base_url(base_url: str) -> str:
    """Normalize local OpenAI-compatible endpoints to the SDK's expected base URL."""
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    return endpoint


def resolve_model_config_value(value: str | None, *, field_name: str) -> str | None:
    """Resolve model config strings that reference environment variables."""
    if not value:
        return value
    if value.startswith("env:"):
        env_name = value.removeprefix("env:").strip()
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ValueError(f"{field_name} environment variable is not set: {env_name}")
        return resolved
    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1].strip()
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ValueError(f"{field_name} environment variable is not set: {env_name}")
        return resolved
    return value
