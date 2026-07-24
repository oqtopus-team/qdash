from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from qdash.copilot.agent import (
    _build_messages,
    _run_litellm_completion,
    _run_litellm_completion_with_tools,
    _run_litellm_responses,
    run_analysis,
)
from qdash.copilot.agent_runtime.client import build_litellm_kwargs
from qdash.copilot.agent_runtime.execution import (
    build_provider_response_schema,
    get_max_tool_rounds,
)
from qdash.copilot.agent_runtime.parsing import parse_response
from qdash.copilot.agent_runtime.schemas import BLOCKS_RESPONSE_SCHEMA
from qdash.copilot.config import CopilotConfig, ModelConfig
from qdash.copilot.contracts import TaskAnalysisContext


def test_parse_response_accepts_ai_review_markdown_without_json() -> None:
    response = parse_response(
        "\n".join(
            [
                "**AI review**",
                "- Decision: `PASS_WITH_NOTE`",
                "- Human label suggestion: `CORRECT`",
                "- Accepted parameter(s): f01",
                "- Needs review: none",
                "- Primary reason: f01 is visually supported.",
                "- Closest knowledge case: q61",
                "- Suggested labels: weak_f12",
                "- Recommended action: Update f01 and keep note.",
                "- Optional note: f12 is weak.",
            ]
        )
    )

    assert response.assessment == "warning"
    assert response.summary == "f01 is visually supported."
    assert response.potential_issues == []
    assert response.recommendations == ["Update f01 and keep note."]
    assert "- Decision: PASS_WITH_NOTE" in response.explanation


def test_parse_response_converts_missing_review_json_to_safe_review() -> None:
    response = parse_response(
        '{"summary":"解析完了","assessment":"warning","explanation":"解析完了"}'
    )

    assert response.assessment == "warning"
    assert response.summary == "AI review response did not include the required review block."
    assert response.explanation.startswith("**AI review**")
    assert "- Decision: `REVIEW`" in response.explanation
    assert "- Suggested labels: `model_format_error`" in response.explanation


def test_parse_response_converts_plain_missing_review_text_to_safe_review() -> None:
    response = parse_response("解析完了")

    assert response.assessment == "warning"
    assert response.summary == "AI review response did not include the required review block."
    assert response.explanation.startswith("**AI review**")
    assert "- Decision: `REVIEW`" in response.explanation
    assert "- Suggested labels: `model_format_error`" in response.explanation


def test_blocks_response_schema_uses_nullable_assessment() -> None:
    assessment_schema = BLOCKS_RESPONSE_SCHEMA["properties"]["assessment"]

    assert assessment_schema == {
        "type": ["string", "null"],
        "enum": ["good", "warning", "bad", None],
    }


def test_blocks_response_schema_allows_chart_blocks() -> None:
    block_schema = BLOCKS_RESPONSE_SCHEMA["properties"]["blocks"]["items"]

    assert block_schema["properties"]["type"] == {"type": "string", "enum": ["text", "chart"]}
    assert block_schema["properties"]["chart"] == {"type": ["object", "null"]}
    assert block_schema["additionalProperties"] is False


def test_blocks_response_schema_sets_additional_properties_false_on_objects() -> None:
    def assert_object_schemas_are_closed(schema: Any) -> None:
        if isinstance(schema, dict):
            if schema.get("type") == "object":
                assert schema.get("additionalProperties") is False
            for value in schema.values():
                assert_object_schemas_are_closed(value)
        elif isinstance(schema, list):
            for item in schema:
                assert_object_schemas_are_closed(item)

    assert_object_schemas_are_closed(BLOCKS_RESPONSE_SCHEMA)


def test_build_provider_response_schema_makes_blocks_response_bedrock_compatible() -> None:
    config = CopilotConfig(model=ModelConfig(provider="bedrock", name="jp.anthropic.claude"))

    schema = build_provider_response_schema(BLOCKS_RESPONSE_SCHEMA, config)

    assert schema is not BLOCKS_RESPONSE_SCHEMA
    assert schema["properties"]["assessment"] == {
        "type": "string",
        "enum": ["good", "warning", "bad"],
    }
    block_properties = schema["properties"]["blocks"]["items"]["properties"]
    assert block_properties["type"] == {"type": "string", "enum": ["text"]}
    assert block_properties["content"] == {"type": "string"}
    assert block_properties["chart"] == {"type": "null"}


def test_build_provider_response_schema_leaves_non_bedrock_schema_unchanged() -> None:
    config = CopilotConfig(model=ModelConfig(provider="ollama", name="gemma4:27b"))

    schema = build_provider_response_schema(BLOCKS_RESPONSE_SCHEMA, config)

    assert schema is BLOCKS_RESPONSE_SCHEMA


def test_build_messages_includes_multiple_target_images_with_labels() -> None:
    messages = _build_messages(
        "system",
        "review",
        image_base64="raw",
        conversation_history=None,
        expected_images=None,
        experiment_images=[("raw", "target raw"), ("marked", "target marked")],
    )

    content = messages[-1]["content"]
    texts = [part["text"] for part in content if part["type"] == "text"]
    images = [part for part in content if part["type"] == "image_url"]

    assert "Actual experimental result images:" in texts
    assert "[Target: target raw]" in texts
    assert "[Target: target marked]" in texts
    assert len(images) == 2


def test_build_litellm_kwargs_uses_provider_specific_model_strings(monkeypatch) -> None:
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("AWS_BASE_URL", "https://bedrock-runtime.us-west-2.amazonaws.com")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "openai/Gemma-4-31B-IT-NVFP4")
    monkeypatch.setenv("VLLM_BASE_URL", "http://10.20.10.19:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "EMPTY")

    bedrock = build_litellm_kwargs(
        CopilotConfig(model=ModelConfig(provider="bedrock", name="jp.anthropic.claude"))
    )
    ollama = build_litellm_kwargs(
        CopilotConfig(
            model=ModelConfig(
                provider="ollama",
                name="gemma4:31b",
                base_url="env:OLLAMA_BASE_URL",
            )
        )
    )
    openai = build_litellm_kwargs(
        CopilotConfig(
            model=ModelConfig(provider="openai", name="gpt-5.4", api_key_env="OPENAI_API_KEY")
        )
    )
    vllm = build_litellm_kwargs(
        CopilotConfig(
            model=ModelConfig(
                provider="vllm",
                name="env:LITELLM_MODEL",
                base_url="env:VLLM_BASE_URL",
                api_key_env="VLLM_API_KEY",
            )
        )
    )

    assert bedrock["model"] == "bedrock/jp.anthropic.claude"
    assert bedrock["api_base"] == "https://bedrock-runtime.us-west-2.amazonaws.com"
    assert bedrock["aws_region_name"] == "us-west-2"
    assert bedrock["api_key"] == "bedrock-token"
    assert bedrock["aws_access_key_id"] == "bedrock-api-key"
    assert bedrock["aws_secret_access_key"] == "bedrock-api-key"  # noqa: S105
    assert ollama == {"model": "ollama_chat/gemma4:31b", "api_base": "http://ollama:11434"}
    assert openai == {"model": "openai/gpt-5.4", "api_key": "test-key"}
    assert vllm == {
        "model": "openai/Gemma-4-31B-IT-NVFP4",
        "api_base": "http://10.20.10.19:8000/v1",
        "api_key": "EMPTY",
    }


def test_build_litellm_kwargs_requires_bedrock_bearer_token(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("AWS_BASE_URL", "https://bedrock-runtime.us-west-2.amazonaws.com")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ignored-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ignored-secret-key")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "ignored-session-token")
    monkeypatch.setenv("AWS_PROFILE", "ignored-profile")

    with pytest.raises(ValueError, match="AWS_BEARER_TOKEN_BEDROCK"):
        build_litellm_kwargs(
            CopilotConfig(model=ModelConfig(provider="bedrock", name="jp.anthropic.claude"))
        )


@pytest.mark.asyncio
async def test_run_litellm_completion_passes_ollama_options() -> None:
    captured = {}

    async def _completion(_config, **kwargs):
        captured.update(build_litellm_kwargs(_config))
        captured.update(kwargs)
        message = SimpleNamespace(content='{"summary":"ok","explanation":"ok"}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    config = CopilotConfig(
        model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            keep_alive="30m",
            num_ctx=8192,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
            reasoning_effort="none",
        )
    )

    with patch("qdash.copilot.agent_runtime.execution.litellm_completion", new=_completion):
        await _run_litellm_completion([{"role": "user", "content": "hi"}], config)

    assert captured["model"] == "ollama_chat/gemma4:26b"
    assert captured["extra_body"] == {
        "keep_alive": "30m",
        "options": {"num_ctx": 8192, "top_k": 64},
    }
    assert captured["temperature"] == 1.0
    assert captured["top_p"] == 0.95
    assert captured["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_run_litellm_completion_uses_reasoning_when_content_is_empty() -> None:
    async def _completion(_config, **_kwargs):
        message = SimpleNamespace(content="", reasoning="reasoning review text")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    config = CopilotConfig(
        model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            temperature=0,
        )
    )

    with patch("qdash.copilot.agent_runtime.execution.litellm_completion", new=_completion):
        content = await _run_litellm_completion([{"role": "user", "content": "hi"}], config)

    assert content == "reasoning review text"


def test_get_max_tool_rounds_uses_higher_budget_for_ollama() -> None:
    ollama_config = CopilotConfig(model=ModelConfig(provider="ollama", name="gemma4:27b"))
    openai_config = CopilotConfig(model=ModelConfig(provider="openai", name="gpt-5"))

    assert get_max_tool_rounds(ollama_config) == 16
    assert get_max_tool_rounds(openai_config) == 10


@pytest.mark.asyncio
async def test_run_litellm_responses_finalizes_after_repeated_identical_tool_calls() -> None:
    captured_final_input: list[dict[str, Any]] = []

    class _FunctionCallItem:
        type = "function_call"

        def __init__(self, *, name: str, arguments: str, call_id: str) -> None:
            self.name = name
            self.arguments = arguments
            self.call_id = call_id

        def model_dump(self) -> dict[str, Any]:
            return {
                "type": "function_call",
                "name": self.name,
                "arguments": self.arguments,
                "call_id": self.call_id,
            }

    calls = 0

    async def _responses(_config, **kwargs):
        nonlocal calls
        calls += 1
        if calls <= 4:
            return SimpleNamespace(
                output=[
                    _FunctionCallItem(
                        name="execute_python_analysis",
                        arguments='{"code":"result = 1"}',
                        call_id=f"call-{calls}",
                    )
                ],
                output_text=None,
            )

        nonlocal captured_final_input
        captured_final_input = kwargs["input"]
        return SimpleNamespace(
            output=[],
            output_text='{"blocks":[{"type":"text","content":"best effort","chart":null}],"assessment":"warning"}',
        )

    config = CopilotConfig(
        model=ModelConfig(
            provider="ollama",
            name="gemma4:27b",
            temperature=0,
        )
    )

    with patch("qdash.copilot.agent_runtime.execution.litellm_responses", new=_responses):
        content = await _run_litellm_responses(
            "system",
            [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            config,
            {"execute_python_analysis": lambda _args: {"output": "ok"}},
        )

    assert "best effort" in content
    assert captured_final_input[-1]["role"] == "user"
    assert "Do not call any more tools." in captured_final_input[-1]["content"][0]["text"]
    assert (
        "Detected repeated identical tool calls" in captured_final_input[-1]["content"][0]["text"]
    )


@pytest.mark.asyncio
async def test_run_litellm_completion_with_tools_keeps_tools_for_bedrock_finalization(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-token")

    captured_final_kwargs: dict[str, Any] = {}
    calls = 0

    async def _completion(_config, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            tool_call = SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(
                    name="execute_python_analysis",
                    arguments='{"code":"result = 1"}',
                ),
            )
            message = SimpleNamespace(content="", tool_calls=[tool_call])
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        if calls == 2:
            message = SimpleNamespace(content="", tool_calls=[])
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        captured_final_kwargs.update(kwargs)
        message = SimpleNamespace(
            content='{"blocks":[{"type":"text","content":"done","chart":null}],"assessment":"good"}',
            tool_calls=[],
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    config = CopilotConfig(
        model=ModelConfig(
            provider="bedrock",
            name="jp.anthropic.claude",
            temperature=0,
        )
    )

    with patch("qdash.copilot.agent_runtime.execution.litellm_completion", new=_completion):
        content = await _run_litellm_completion_with_tools(
            [{"role": "user", "content": "hi"}],
            config,
            {"execute_python_analysis": lambda _args: {"output": "ok"}},
            response_schema=BLOCKS_RESPONSE_SCHEMA,
        )

    assert "done" in content
    assert "tools" in captured_final_kwargs
    assert captured_final_kwargs["tool_choice"] == "auto"
    final_schema = captured_final_kwargs["response_format"]["json_schema"]["schema"]
    assert final_schema["properties"]["assessment"] == {
        "type": "string",
        "enum": ["good", "warning", "bad"],
    }


@pytest.mark.asyncio
async def test_run_analysis_uses_litellm_completion_for_completion_api_style() -> None:
    config = CopilotConfig(
        response_language="ja",
        model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            temperature=0,
            api_style="completion",
        ),
        analysis_model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            temperature=0,
            api_style="completion",
        ),
    )
    context = TaskAnalysisContext(
        task_knowledge_prompt="knowledge",
        chip_id="chip",
        qid="0",
    )
    captured = {}

    async def _completion(_config, **kwargs):
        captured.update(build_litellm_kwargs(_config))
        captured.update(kwargs)
        message = SimpleNamespace(
            content='{"blocks":[{"type":"text","content":"日本語で整形しました。","chart":null}],"assessment":"good"}'
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    with patch("qdash.copilot.agent_runtime.execution.litellm_completion", new=_completion):
        result = await run_analysis(
            context=context,
            user_message="analyze",
            config=config,
        )

    assert captured["model"] == "ollama_chat/gemma4:26b"
    assert result["blocks"][0]["content"] == "日本語で整形しました。"
