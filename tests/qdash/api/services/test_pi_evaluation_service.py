"""Tests for the planner-less evaluation call to the Pi Agent Runtime."""

from __future__ import annotations

import json

import httpx
import pytest

from qdash.api.services.pi_chat_service import QDashAuth
from qdash.api.services.pi_evaluation_service import (
    EvaluationRuntimeError,
    evaluate_task_result,
)

AUTH = QDashAuth(access_token="user-token", project_id="proj")


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_the_runtime_record_is_returned_as_is(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-secret")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"task_id": "t1", "evaluation": {"model": "vllm/x"}})

    record = await evaluate_task_result(
        "t1", auth=AUTH, question="Why?", transport=_transport(handler)
    )

    assert record == {"task_id": "t1", "evaluation": {"model": "vllm/x"}}
    assert isinstance(seen["url"], str)
    assert seen["url"].endswith("/evaluate")
    assert seen["body"] == {"task_id": "t1", "mode": "direct", "question": "Why?"}
    assert isinstance(seen["headers"], dict)
    assert seen["headers"]["authorization"] == "Bearer runtime-secret"
    assert seen["headers"]["x-qdash-token"] == "user-token"
    assert seen["headers"]["x-qdash-project-id"] == "proj"


@pytest.mark.asyncio
async def test_a_runtime_error_names_its_stage(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "task t1 has no figure", "stage": "evidence"})

    with pytest.raises(EvaluationRuntimeError) as excinfo:
        await evaluate_task_result("t1", auth=AUTH, transport=_transport(handler))

    assert excinfo.value.stage == "evidence"
    assert excinfo.value.detail == "task t1 has no figure"
    assert str(excinfo.value) == "evidence: task t1 has no figure"


@pytest.mark.asyncio
async def test_a_non_json_failure_reports_the_status(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(EvaluationRuntimeError) as excinfo:
        await evaluate_task_result("t1", auth=AUTH, transport=_transport(handler))

    assert excinfo.value.stage == "runtime"
    assert excinfo.value.detail == "HTTP 502"


@pytest.mark.asyncio
async def test_planner_mode_sends_the_planner_model(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_RUNTIME_TOKEN", "runtime-secret")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"task_id": "t1"})

    await evaluate_task_result(
        "t1",
        auth=AUTH,
        mode="planner",
        model={"provider": "openai-compatible", "name": "qwen"},
        thinking_level="low",
        transport=_transport(handler),
    )

    assert seen["body"] == {
        "task_id": "t1",
        "mode": "planner",
        "model": {"provider": "openai-compatible", "name": "qwen"},
        "thinking_level": "low",
    }
