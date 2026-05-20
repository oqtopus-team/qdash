from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.copilot.agent import (
    _build_messages,
    _run_chat_completions,
    _run_responses_api,
    run_analysis,
)
from qdash.copilot.agent_runtime.execution import get_max_tool_rounds
from qdash.copilot.agent_runtime.parsing import parse_response
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


@pytest.mark.asyncio
async def test_run_chat_completions_passes_ollama_options() -> None:
    captured = {}

    class _Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content='{"summary":"ok","explanation":"ok"}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client: Any = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
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

    await _run_chat_completions(client, [{"role": "user", "content": "hi"}], config)

    assert captured["extra_body"] == {
        "keep_alive": "30m",
        "options": {"num_ctx": 8192, "top_k": 64},
    }
    assert captured["temperature"] == 1.0
    assert captured["top_p"] == 0.95
    assert captured["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_run_chat_completions_uses_reasoning_when_content_is_empty() -> None:
    class _Completions:
        async def create(self, **kwargs):
            message = SimpleNamespace(content="", reasoning="reasoning review text")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client: Any = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    config = CopilotConfig(
        model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            temperature=0,
        )
    )

    content = await _run_chat_completions(client, [{"role": "user", "content": "hi"}], config)

    assert content == "reasoning review text"


def test_get_max_tool_rounds_uses_higher_budget_for_ollama() -> None:
    ollama_config = CopilotConfig(model=ModelConfig(provider="ollama", name="gemma4:27b"))
    openai_config = CopilotConfig(model=ModelConfig(provider="openai", name="gpt-5"))

    assert get_max_tool_rounds(ollama_config) == 16
    assert get_max_tool_rounds(openai_config) == 10


@pytest.mark.asyncio
async def test_run_responses_api_finalizes_after_repeated_identical_tool_calls() -> None:
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

    class _Responses:
        def __init__(self) -> None:
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            if self.calls <= 4:
                return SimpleNamespace(
                    output=[
                        _FunctionCallItem(
                            name="execute_python_analysis",
                            arguments='{"code":"result = 1"}',
                            call_id=f"call-{self.calls}",
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

    client: Any = SimpleNamespace(responses=_Responses())
    config = CopilotConfig(
        model=ModelConfig(
            provider="ollama",
            name="gemma4:27b",
            temperature=0,
        )
    )

    content = await _run_responses_api(
        client,
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
async def test_run_analysis_translates_ollama_output_when_target_language_mismatches() -> None:
    client: Any = SimpleNamespace()
    config = CopilotConfig(
        response_language="ja",
        model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            temperature=0,
        ),
        analysis_model=ModelConfig(
            provider="ollama",
            name="gemma4:26b",
            temperature=0,
        ),
    )
    context = TaskAnalysisContext(
        task_knowledge_prompt="knowledge",
        chip_id="chip",
        qid="0",
    )
    translated = parse_response(
        "\n".join(
            [
                "**AI review**",
                "- Decision: `PASS`",
                "- Human label suggestion: `CORRECT`",
                "- Accepted parameter(s): f01",
                "- Needs review: none",
                "- Primary reason: 日本語で整形しました。",
                "- Closest knowledge case: none",
                "- Suggested labels: none",
                "- Recommended action: accept",
            ]
        )
    )

    with (
        patch("qdash.copilot.agent._build_client", return_value=client),
        patch(
            "qdash.copilot.agent._run_chat_completions",
            new=AsyncMock(
                return_value='{"summary":"한국어 요약","assessment":"good","explanation":"검토 분류\\n결정: PASS"}'
            ),
        ),
        patch(
            "qdash.copilot.agent._translate_analysis_response",
            new=AsyncMock(return_value=translated),
        ) as translate_mock,
    ):
        result = await run_analysis(
            context=context,
            user_message="analyze",
            config=config,
        )

    translate_mock.assert_awaited_once()
    assert result["blocks"][0]["content"].startswith("**AI review**")
