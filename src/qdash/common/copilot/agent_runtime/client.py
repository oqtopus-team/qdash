"""OpenAI-compatible client construction helpers for Copilot agents."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from qdash.common.copilot.settings import CopilotConfig


def build_client(config: CopilotConfig) -> AsyncOpenAI:
    """Build an AsyncOpenAI client based on provider configuration."""
    provider = config.model.provider
    base_url = resolve_model_config_value(config.model.base_url, field_name="base_url")
    api_key_env = config.model.api_key_env

    if provider == "ollama":
        default_endpoint = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        endpoint = (base_url or default_endpoint).rstrip("/")
        if not endpoint.endswith("/v1"):
            endpoint = f"{endpoint}/v1"
        key_env = api_key_env or "OLLAMA_API_KEY"
        return AsyncOpenAI(base_url=endpoint, api_key=os.environ.get(key_env, "ollama"))
    if provider == "openai":
        if base_url:
            base_url = normalize_openai_compatible_base_url(base_url)
            key = os.environ.get(api_key_env or "OPENAI_API_KEY", "local")
            return AsyncOpenAI(base_url=base_url, api_key=key)
        return AsyncOpenAI(api_key=os.environ.get(api_key_env or "OPENAI_API_KEY"))
    if provider == "anthropic":
        raise ValueError(
            "Anthropic provider is not supported with openai SDK. Use openai or ollama."
        )
    raise ValueError(f"Unknown LLM provider: {provider}")


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
