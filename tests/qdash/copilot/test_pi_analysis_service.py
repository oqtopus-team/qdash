"""Tests for the Pi backend of the analysis sidebar."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qdash.api.services import pi_analysis_service, pi_chat_service
from qdash.copilot.config import CopilotConfig, ModelConfig
from qdash.copilot.contracts import AnalysisContextResult, AnalyzeRequest, TaskAnalysisContext
from qdash.copilot.prompts.analysis import build_language_instruction

_IMAGES_SENT = {
    "experiment_figure": True,
    "experiment_figure_paths": ["fig.png"],
    "expected_images": [{"alt_text": "expected image", "index": 0}],
    "task_name": "CheckQubitSpectroscopy",
}


def _config() -> CopilotConfig:
    return CopilotConfig(
        enabled=True,
        copilot_backend="pi",
        model=ModelConfig(provider="ollama", name="gemma4:31b", reasoning_effort="none"),
    )


def _bundle() -> AnalysisContextResult:
    return AnalysisContextResult(
        context=TaskAnalysisContext(
            task_knowledge_prompt="knowledge-v1",
            chip_id="chip-1",
            qid="4",
            output_parameters={"coarse_qubit_frequency": {"value": 4.21}},
        ),
        image_base64="experiment-b64",
        expected_images=[("expected-b64", "expected image")],
        figure_paths=["fig.png"],
    )


def _request(message: str = "Is this result trustworthy?") -> AnalyzeRequest:
    return AnalyzeRequest(
        task_name="CheckQubitSpectroscopy",
        chip_id="chip-1",
        qid="4",
        execution_id="exec-1",
        task_id="task-1",
        message=message,
        session_id="session-1",
        request_id="request-1",
    )


def test_auto_language_follows_the_latest_user_message() -> None:
    config = _config().model_copy(update={"response_language": "auto"})

    instruction = build_language_instruction(config)

    assert "same language as the user's latest message" in instruction


async def _collect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stored: list[dict[str, Any]],
    ndjson: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]], list[list[dict[str, Any]]]]:
    """Run one turn against a stubbed runtime, returning payload, events and writes."""
    captured: dict[str, Any] = {}
    saved: list[list[dict[str, Any]]] = []
    lines = ndjson or [{"type": "done", "text": "Looks good", "messages": [{"role": "user"}]}]

    async def ensure_agent_session(_username: str, _session_id: str) -> None:
        return None

    monkeypatch.setattr(pi_chat_service, "ensure_agent_session", ensure_agent_session)

    async def fake_stream_payload(payload, *, step, extra_result=None):
        captured["payload"] = payload
        captured["step"] = step

        async def _lines():
            for line in lines:
                yield json.dumps(line)

        async for event in pi_chat_service.translate(_lines(), extra_result=extra_result):
            yield event

    monkeypatch.setattr(pi_chat_service, "stream_payload", fake_stream_payload)

    events = [
        _parse(sse)
        async for sse in pi_analysis_service.stream(
            _request(),
            _config(),
            _bundle(),
            username="alice",
            language_instruction="Always respond in English.",
            images_sent=_IMAGES_SENT,
        )
    ]
    return captured, events, saved


def _parse(sse: str) -> tuple[str, dict[str, Any]]:
    name, data = sse.strip().split("\n", 1)
    return name.removeprefix("event: "), json.loads(data.removeprefix("data: "))


class TestBuildAnalysisPrompt:
    def test_carries_context_task_and_figure_counts(self) -> None:
        prompt = pi_analysis_service.build_analysis_prompt(
            bundle=_bundle(),
            config=_config(),
            user_message="Is this trustworthy?",
            language_instruction="Always respond in English.",
        )

        assert "knowledge-v1" in prompt
        assert "1 expected reference figure(s) first, then 1 figure(s)" in prompt
        assert prompt.endswith("## Your task\n\nIs this trustworthy?")

    def test_tells_the_model_to_answer_from_the_provided_context(self) -> None:
        prompt = pi_analysis_service.build_analysis_prompt(
            bundle=_bundle(),
            config=_config(),
            user_message="hi",
            language_instruction="",
        )

        guidance = prompt.index("## How to answer")
        assert guidance < prompt.index("## Your task")
        assert "Do not re-fetch this result" in prompt

    def test_does_not_request_the_blocks_json_schema(self) -> None:
        prompt = pi_analysis_service.build_analysis_prompt(
            bundle=_bundle(),
            config=_config(),
            user_message="hi",
            language_instruction="",
        )

        assert "valid JSON object" not in prompt

    def test_keeps_the_ai_review_markdown_skeleton(self) -> None:
        prompt = pi_analysis_service.build_analysis_prompt(
            bundle=_bundle(),
            config=_config(),
            user_message="hi",
            language_instruction="",
        )

        assert "**AI review**" in prompt


class TestStream:
    @pytest.mark.asyncio
    async def test_session_creation_failure_blocks_runtime_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fail(_username: str, _session_id: str) -> None:
            raise RuntimeError("database unavailable")

        runtime = pytest.fail
        monkeypatch.setattr(pi_chat_service, "ensure_agent_session", fail)
        monkeypatch.setattr(pi_chat_service, "stream_payload", runtime)

        events = [
            _parse(sse)
            async for sse in pi_analysis_service.stream(
                _request(),
                _config(),
                _bundle(),
                username="alice",
                language_instruction="",
                images_sent=_IMAGES_SENT,
            )
        ]

        assert events == [
            (
                "error",
                {"step": "init", "detail": "Could not persist the analysis session"},
            )
        ]

    @pytest.mark.asyncio
    async def test_first_turn_sends_context_and_figures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured, _, _ = await _collect(monkeypatch, stored=[])

        payload = captured["payload"]
        assert payload["owner_id"] == "alice"
        assert payload["request_id"] == "request-1"
        assert payload["message"] == "Is this result trustworthy?"
        assert "knowledge-v1" in payload["initial_message"]
        assert [image["data"] for image in payload["images"]] == [
            "expected-b64",
            "experiment-b64",
        ]
        assert payload["thinking_level"] == "off"
        assert captured["step"] == "run_analysis"

    @pytest.mark.asyncio
    async def test_runtime_decides_whether_to_use_opening_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured, _, _ = await _collect(monkeypatch, stored=[{"role": "user"}])

        payload = captured["payload"]
        assert payload["message"] == "Is this result trustworthy?"
        assert "knowledge-v1" in payload["initial_message"]
        assert payload["images"]

    @pytest.mark.asyncio
    async def test_images_sent_rides_on_the_result_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, events, saved = await _collect(monkeypatch, stored=[])

        name, result = events[-1]
        assert name == "result"
        assert result["images_sent"] == _IMAGES_SENT
        assert result["blocks"] == [{"type": "text", "content": "Looks good", "chart": None}]
        assert saved == []

    @pytest.mark.asyncio
    async def test_missing_session_id_is_rejected(self) -> None:
        request = _request().model_copy(update={"session_id": None})

        events = [
            _parse(sse)
            async for sse in pi_analysis_service.stream(
                request,
                _config(),
                _bundle(),
                username="alice",
                language_instruction="",
                images_sent=_IMAGES_SENT,
            )
        ]

        assert events == [
            (
                "error",
                {
                    "step": "init",
                    "detail": "session_id is required by the Pi analysis backend",
                },
            )
        ]
