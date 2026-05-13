from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.common.copilot.agent import _run_chat_completions, run_analysis
from qdash.common.copilot.agent_runtime.parsing import parse_response
from qdash.common.copilot.config import CopilotConfig, ModelConfig
from qdash.common.copilot.contracts import TaskAnalysisContext


def test_parse_response_accepts_review_triage_markdown_without_json() -> None:
    response = parse_response(
        "\n".join(
            [
                "**Review triage**",
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


def test_parse_response_converts_missing_triage_json_to_safe_review() -> None:
    response = parse_response(
        '{"summary":"解析完了","assessment":"warning","explanation":"解析完了"}'
    )

    assert response.assessment == "warning"
    assert response.summary == "AI triage response did not include the required review block."
    assert response.explanation.startswith("**Review triage**")
    assert "- Decision: `REVIEW`" in response.explanation
    assert "- Suggested labels: `model_format_error`" in response.explanation


def test_parse_response_converts_plain_missing_triage_text_to_safe_review() -> None:
    response = parse_response("解析完了")

    assert response.assessment == "warning"
    assert response.summary == "AI triage response did not include the required review block."
    assert response.explanation.startswith("**Review triage**")
    assert "- Decision: `REVIEW`" in response.explanation
    assert "- Suggested labels: `model_format_error`" in response.explanation


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
            message = SimpleNamespace(content="", reasoning="reasoning triage text")
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

    assert content == "reasoning triage text"


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
                "**Review triage**",
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
        patch("qdash.common.copilot.agent._build_client", return_value=client),
        patch(
            "qdash.common.copilot.agent._run_chat_completions",
            new=AsyncMock(
                return_value='{"summary":"한국어 요약","assessment":"good","explanation":"검토 분류\\n결정: PASS"}'
            ),
        ),
        patch(
            "qdash.common.copilot.agent._translate_analysis_response",
            new=AsyncMock(return_value=translated),
        ) as translate_mock,
    ):
        result = await run_analysis(
            context=context,
            user_message="analyze",
            config=config,
        )

    translate_mock.assert_awaited_once()
    assert result["blocks"][0]["content"].startswith("**Review triage**")
