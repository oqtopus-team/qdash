"""Tests for task API routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from qdash.api.routers.task import quick_run_task
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.schemas.task import QuickRunTaskRequest


def _project_context() -> SimpleNamespace:
    return SimpleNamespace(
        project_id="project-1",
        user=SimpleNamespace(username="alice"),
    )


@pytest.mark.asyncio
async def test_quick_run_task_rejects_disabled_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qdash.api.routers.task.get_available_backends", lambda: ["fake"])
    monkeypatch.setattr("qdash.api.routers.task.is_task_available", lambda *_args: False)
    flow_service = SimpleNamespace(execute_single_task_from_snapshot=AsyncMock())

    with pytest.raises(HTTPException, match="not enabled") as exc_info:
        await quick_run_task(
            task_name="DisabledTask",
            body=QuickRunTaskRequest(chip_id="chip-1", qid="0", backend_name="fake"),
            ctx=_project_context(),  # type: ignore[arg-type]
            flow_service=flow_service,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    flow_service.execute_single_task_from_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_quick_run_task_resolves_and_validates_default_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("qdash.api.routers.task.get_default_backend", lambda: "fake")
    monkeypatch.setattr("qdash.api.routers.task.get_available_backends", lambda: ["fake"])
    monkeypatch.setattr("qdash.api.routers.task.is_task_available", lambda *_args: True)
    response = ExecuteFlowResponse(
        execution_id="flow-run-1",
        flow_run_url="http://prefect/runs/flow-run/flow-run-1",
        qdash_ui_url="http://qdash/execution/flow-run-1",
        message="started",
    )
    execute = AsyncMock(return_value=response)
    flow_service = SimpleNamespace(execute_single_task_from_snapshot=execute)

    result = await quick_run_task(
        task_name="CheckRabi",
        body=QuickRunTaskRequest(chip_id="chip-1", qid="0"),
        ctx=_project_context(),  # type: ignore[arg-type]
        flow_service=flow_service,  # type: ignore[arg-type]
    )

    assert result == response
    execute.assert_awaited_once()
    assert execute.await_args_list[0].kwargs["backend_name"] == "fake"
