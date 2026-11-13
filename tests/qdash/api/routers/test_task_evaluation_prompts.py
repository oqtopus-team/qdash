"""Tests for the evaluation prompt preview route."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from qdash.api.routers.task import get_task_evaluation_prompts
from qdash.api.services.pi_evaluation_service import EvaluationRuntimeError

PREVIEW: dict[str, Any] = {
    "task_name": "CheckRabi",
    "with_examples": True,
    "model": "vllm/nvidia/Ising-Calibration",
    "questions": [
        {"key": "fit_reliability", "prompt": "Assess whether the fit [figure] is reliable."},
        {"key": "calibration_diagnosis", "prompt": "Status: ..."},
    ],
    "knowledge": {"chars": 120, "sha256": "ab" * 32},
    "examples": [
        {
            "id": "2026-02-26_tls",
            "title": "TLS coupling",
            "outcome": "suboptimal",
            "status": "SHORT_T1",
            "figures": [{"sha256": "cd" * 32, "mime_type": "image/png", "bytes": 10}],
        }
    ],
    "examples_used": 1,
}


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(project_id="project-1", user=SimpleNamespace(username="alice"))


def _credentials() -> SimpleNamespace:
    return SimpleNamespace(credentials="user-token")


def _drafts(task_name: str = "CheckRabi") -> SimpleNamespace:
    """A draft store holding one draft of `task_name`, recording what was asked for."""
    asked: list[tuple[str, str]] = []

    def get(project_id: str, draft_id: str) -> SimpleNamespace:
        asked.append((project_id, draft_id))
        return SimpleNamespace(task_name=task_name)

    return SimpleNamespace(get=get, asked=asked)


@pytest.mark.asyncio
async def test_the_preview_is_requested_as_the_user_and_mapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview = AsyncMock(return_value=PREVIEW)
    monkeypatch.setattr("qdash.api.routers.task.preview_evaluation_prompts", preview)

    response = await get_task_evaluation_prompts(
        task_name="CheckRabi",
        ctx=_ctx(),  # type: ignore[arg-type]
        credentials=_credentials(),  # type: ignore[arg-type]
        drafts=_drafts(),  # type: ignore[arg-type]
        with_examples=True,
        knowledge_draft_id=None,
    )

    preview.assert_awaited_once()
    args, kwargs = preview.await_args
    assert args == ("CheckRabi",)
    assert kwargs["auth"].access_token == _credentials().credentials
    assert kwargs["auth"].project_id == "project-1"
    assert kwargs["with_examples"] is True
    assert kwargs["knowledge_draft_id"] is None
    assert response.task_name == "CheckRabi"
    assert response.with_examples is True
    assert response.model == "vllm/nvidia/Ising-Calibration"
    assert [q.key for q in response.questions] == ["fit_reliability", "calibration_diagnosis"]
    assert response.questions[0].prompt.startswith("Assess whether the fit [figure]")
    assert response.knowledge_chars == 120
    assert response.knowledge_sha256 == "ab" * 32
    assert response.examples[0].id == "2026-02-26_tls"
    assert response.examples[0].status == "SHORT_T1"
    assert response.examples[0].figures[0].sha256 == "cd" * 32
    assert response.examples_used == 1


@pytest.mark.asyncio
async def test_missing_fields_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview = AsyncMock(return_value={"task_name": "CheckRabi", "questions": []})
    monkeypatch.setattr("qdash.api.routers.task.preview_evaluation_prompts", preview)

    response = await get_task_evaluation_prompts(
        task_name="CheckRabi",
        ctx=_ctx(),  # type: ignore[arg-type]
        credentials=_credentials(),  # type: ignore[arg-type]
        drafts=_drafts(),  # type: ignore[arg-type]
        with_examples=False,
        knowledge_draft_id=None,
    )

    assert response.with_examples is False
    assert response.model is None
    assert response.questions == []
    assert response.knowledge_chars is None
    assert response.knowledge_sha256 is None
    assert response.examples == []
    assert response.examples_used == 0


@pytest.mark.asyncio
async def test_runtime_errors_map_to_502_and_unreachable_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = AsyncMock(side_effect=EvaluationRuntimeError("evaluation", "no reference"))
    monkeypatch.setattr("qdash.api.routers.task.preview_evaluation_prompts", failing)
    with pytest.raises(HTTPException) as exc_info:
        await get_task_evaluation_prompts(
            task_name="CheckRabi",
            ctx=_ctx(),  # type: ignore[arg-type]
            credentials=_credentials(),  # type: ignore[arg-type]
            drafts=_drafts(),  # type: ignore[arg-type]
            with_examples=False,
            knowledge_draft_id=None,
        )
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "evaluation: no reference"

    down = AsyncMock(side_effect=httpx.ConnectError("refused"))
    monkeypatch.setattr("qdash.api.routers.task.preview_evaluation_prompts", down)
    with pytest.raises(HTTPException) as exc_info:
        await get_task_evaluation_prompts(
            task_name="CheckRabi",
            ctx=_ctx(),  # type: ignore[arg-type]
            credentials=_credentials(),  # type: ignore[arg-type]
            drafts=_drafts(),  # type: ignore[arg-type]
            with_examples=False,
            knowledge_draft_id=None,
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_a_draft_of_the_task_is_passed_on_and_another_tasks_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview = AsyncMock(return_value=PREVIEW)
    monkeypatch.setattr("qdash.api.routers.task.preview_evaluation_prompts", preview)
    drafts = _drafts()

    await get_task_evaluation_prompts(
        task_name="CheckRabi",
        ctx=_ctx(),  # type: ignore[arg-type]
        credentials=_credentials(),  # type: ignore[arg-type]
        drafts=drafts,  # type: ignore[arg-type]
        with_examples=True,
        knowledge_draft_id="ab" * 32,
    )

    assert drafts.asked == [("project-1", "ab" * 32)]
    await_args = preview.await_args
    assert await_args is not None
    assert await_args.kwargs["knowledge_draft_id"] == "ab" * 32

    preview.reset_mock()
    with pytest.raises(HTTPException) as exc_info:
        await get_task_evaluation_prompts(
            task_name="CheckRabi",
            ctx=_ctx(),  # type: ignore[arg-type]
            credentials=_credentials(),  # type: ignore[arg-type]
            drafts=_drafts("CheckT1"),  # type: ignore[arg-type]
            with_examples=False,
            knowledge_draft_id="ab" * 32,
        )
    assert exc_info.value.status_code == 400
    preview.assert_not_awaited()
