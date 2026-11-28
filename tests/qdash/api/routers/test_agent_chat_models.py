"""The chat model menus offer only models whose API key the agent runtime has.

The runtime holds the model credentials and answers ``GET /chat-models`` with each
configured chat model and whether it is available. These tests fake that answer and
check what the API offers, which model a chat without a choice runs, and that no
credential leaves the API.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from qdash.agent.config import (
    AgentConfig,
    ModelConfig,
    NoChatModelAvailableError,
    available_chat_models,
    select_chat_model,
)
from qdash.agent.contracts import ChatRequest
from qdash.api.routers import agent
from qdash.api.services import pi_chat_service

OPENAI = ModelConfig(provider="openai", name="gpt-6-sol", reasoning_effort="medium")
QWEN = ModelConfig(
    provider="openai-compatible-chat",
    name="qwen3.8-flash-next",
    api_style="completion",
    base_url="env:OPENAI_COMPATIBLE_BASE_URL_CHAT",
    api_key_env="OPENAI_COMPATIBLE_API_KEY_CHAT",
)
ANTHROPIC = ModelConfig(provider="anthropic", name="claude-opus-5-5")
DEEPSEEK = ModelConfig(
    provider="openai-compatible-deepseek",
    name="preview/DeepSeek-V4.1-Flash-1017",
    api_style="completion",
    base_url="env:OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK",
    api_key_env="OPENAI_COMPATIBLE_API_KEY_DEEPSEEK",
)
MODELS = [OPENAI, QWEN, ANTHROPIC, DEEPSEEK]
SECRETS = {
    "OPENAI_API_KEY": "sk-openai-secret-value",
    "ANTHROPIC_API_KEY": "sk-ant-secret-value",
    "OPENAI_COMPATIBLE_API_KEY_DEEPSEEK": "deepseek-secret-value",
}


def _pair(model: ModelConfig) -> tuple[str, str]:
    return (model.provider, model.name)


def _config() -> AgentConfig:
    return AgentConfig(enabled=True, chat_models=MODELS)


def _serve(monkeypatch: pytest.MonkeyPatch, available: list[ModelConfig] | Exception) -> None:
    """Fake the runtime's availability answer, with the keys in the API's environment."""
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)

    async def answer() -> set[tuple[str, str]]:
        if isinstance(available, Exception):
            raise available
        return {_pair(model) for model in available}

    monkeypatch.setattr(pi_chat_service, "available_chat_models", answer)
    monkeypatch.setattr(agent, "load_agent_config", _config)


async def _get_config() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(agent.router, prefix="/agent")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/agent/config")
    assert response.status_code == 200
    body = response.text
    for value in SECRETS.values():
        assert value not in body
    result: dict[str, Any] = response.json()
    return result


def _names(models: list[dict[str, Any]]) -> list[str]:
    return [model["name"] for model in models]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("available", "offered"),
    [
        (MODELS, MODELS),
        ([QWEN, ANTHROPIC, DEEPSEEK], [QWEN, ANTHROPIC, DEEPSEEK]),
        ([OPENAI, QWEN, DEEPSEEK], [OPENAI, QWEN, DEEPSEEK]),
        ([DEEPSEEK, OPENAI], [OPENAI, DEEPSEEK]),
        ([DEEPSEEK], [DEEPSEEK]),
    ],
    ids=["all", "openai-missing", "anthropic-missing", "declared-order", "custom-key-only"],
)
async def test_config_offers_available_models_in_declared_order_default_first(
    monkeypatch: pytest.MonkeyPatch,
    available: list[ModelConfig],
    offered: list[ModelConfig],
) -> None:
    _serve(monkeypatch, available)
    config = await _get_config()

    assert _names(config["chat_models"]) == [model.name for model in offered]
    # The menus label this model as the default, and a chat without a choice runs it.
    assert config["model"]["name"] == offered[0].name
    chosen = await agent._config_with_chat_model(_config(), ChatRequest(message="hi"))
    assert _pair(chosen.model) == _pair(offered[0])


@pytest.mark.asyncio
async def test_config_offers_no_model_when_no_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, [])
    config = await _get_config()

    assert config["chat_models"] == []
    assert config["model"] is None
    with pytest.raises(NoChatModelAvailableError, match="No chat model is available"):
        await agent._config_with_chat_model(_config(), ChatRequest(message="hi"))


@pytest.mark.asyncio
async def test_config_keeps_every_model_when_the_runtime_cannot_be_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, httpx.ConnectError("runtime down"))
    config = await _get_config()

    assert _names(config["chat_models"]) == [model.name for model in MODELS]
    assert config["model"]["name"] == OPENAI.name
    chosen = await agent._config_with_chat_model(_config(), ChatRequest(message="hi"))
    assert _pair(chosen.model) == _pair(OPENAI)


@pytest.mark.asyncio
async def test_an_explicit_choice_is_kept_without_asking_the_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never() -> set[tuple[str, str]]:
        raise AssertionError("an explicit choice needs no availability")

    monkeypatch.setattr(pi_chat_service, "available_chat_models", never)
    request = ChatRequest(message="hi", model_override=ANTHROPIC)
    chosen = await agent._config_with_chat_model(_config(), request)
    assert _pair(chosen.model) == _pair(ANTHROPIC)


def test_selection_without_availability_keeps_the_first_chat_model() -> None:
    config = _config()
    assert select_chat_model(config) == OPENAI
    assert available_chat_models(config, None) == MODELS
    assert select_chat_model(config, available={_pair(ANTHROPIC)}) == ANTHROPIC
    # A config without chat_models still runs its model.
    legacy = AgentConfig(enabled=True, model=OPENAI)
    assert select_chat_model(legacy, available=set()) == OPENAI


@pytest.mark.asyncio
async def test_runtime_availability_is_read_as_names_and_flags_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "chat_models": [
                    {"provider": "openai", "name": "gpt-6-sol", "available": False},
                    {"provider": "anthropic", "name": "claude-opus-5-5", "available": True},
                    {
                        "provider": "openai-compatible-deepseek",
                        "name": DEEPSEEK.name,
                        "available": True,
                    },
                    {"provider": "openai", "name": "truthy", "available": "yes"},
                    {"name": "no-provider", "available": True},
                ]
            },
        )

    real_client = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-token")
    monkeypatch.setattr(httpx, "AsyncClient", client)

    available = await pi_chat_service.available_chat_models()

    assert available == {("anthropic", "claude-opus-5-5"), _pair(DEEPSEEK)}
    assert [(r.method, r.url.path) for r in seen] == [("GET", "/chat-models")]
    assert seen[0].headers["authorization"] == "Bearer runtime-token"
