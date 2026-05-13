from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from qdash.common.copilot.agent import _run_chat_completions
from qdash.common.copilot.agent_runtime.parsing import parse_response
from qdash.common.copilot.config import CopilotConfig, ModelConfig


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
