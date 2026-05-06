from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from qdash.api.lib.copilot_agent import _parse_response, _run_chat_completions
from qdash.api.lib.copilot_config import CopilotConfig, ModelConfig


def test_parse_response_accepts_review_triage_markdown_without_json() -> None:
    response = _parse_response(
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


@pytest.mark.asyncio
async def test_run_chat_completions_passes_ollama_keep_alive_and_num_ctx() -> None:
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
            temperature=0,
        )
    )

    await _run_chat_completions(client, [{"role": "user", "content": "hi"}], config)

    assert captured["extra_body"] == {
        "keep_alive": "30m",
        "options": {"num_ctx": 8192},
    }
