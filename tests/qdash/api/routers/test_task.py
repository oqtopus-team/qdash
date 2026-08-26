"""Tests for task API routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from qdash.api.routers.task import quick_run_task
from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.schemas.task import QuickRunTaskRequest
from qdash.api.schemas.task_file import ListTaskInfoResponse, TaskInfo


def _project_context() -> SimpleNamespace:
    return SimpleNamespace(
        project_id="project-1",
        user=SimpleNamespace(username="alice"),
    )


def _task_file_service(*tasks: TaskInfo) -> SimpleNamespace:
    return SimpleNamespace(
        list_task_info=lambda *_args, **_kwargs: ListTaskInfoResponse(tasks=list(tasks))
    )


def _task_info() -> TaskInfo:
    return TaskInfo(
        name="CheckRabi",
        class_name="CheckRabi",
        task_type="qubit",
        file_path="fake/fake_check_rabi.py",
        input_parameters={
            "qubit_frequency": {"user_override": "allowed", "value_type": "float"},
            "readout_duration": {"user_override": "forbidden", "value_type": "float"},
        },
        run_parameters={
            "shots": {"value_type": "int"},
            "frequency_range": {"value_type": "np.arange"},
            "resonator_assignment_order": {"value_type": "list"},
        },
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
            task_file_service=_task_file_service(),  # type: ignore[arg-type]
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
        flow_run_id="flow-run-1",
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
        task_file_service=_task_file_service(_task_info()),  # type: ignore[arg-type]
    )

    assert result == response
    execute.assert_awaited_once()
    assert execute.await_args_list[0].kwargs["backend_name"] == "fake"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            QuickRunTaskRequest(
                chip_id="chip-1",
                qid="0",
                backend_name="fake",
                input_parameter_overrides={"typo": 1.0},
            ),
            "unknown input parameters: typo",
        ),
        (
            QuickRunTaskRequest(
                chip_id="chip-1",
                qid="0",
                backend_name="fake",
                run_parameter_overrides={"shotz": 100},
            ),
            "unknown run parameters: shotz",
        ),
        (
            QuickRunTaskRequest(
                chip_id="chip-1",
                qid="0",
                backend_name="fake",
                input_parameter_overrides={"readout_duration": 1024},
            ),
            "input parameters do not allow overrides: readout_duration",
        ),
        (
            QuickRunTaskRequest(
                chip_id="chip-1",
                qid="0",
                backend_name="fake",
                input_parameter_overrides={"qubit_frequency": "5.0"},
                run_parameter_overrides={"shots": 100.5},
            ),
            "invalid parameter types: input.qubit_frequency must be float, run.shots must be int",
        ),
        (
            QuickRunTaskRequest(
                chip_id="chip-1",
                qid="0",
                backend_name="fake",
                run_parameter_overrides={"resonator_assignment_order": "[3, 0, 2, 1]"},
            ),
            "invalid parameter types: run.resonator_assignment_order must be list",
        ),
        (
            QuickRunTaskRequest(
                chip_id="chip-1",
                qid="0",
                backend_name="fake",
                run_parameter_overrides={"frequency_range": [5.75, 6.75]},
            ),
            "invalid parameter types: run.frequency_range must be np.arange",
        ),
    ],
)
async def test_quick_run_task_rejects_invalid_overrides(
    monkeypatch: pytest.MonkeyPatch,
    body: QuickRunTaskRequest,
    message: str,
) -> None:
    monkeypatch.setattr("qdash.api.routers.task.get_available_backends", lambda: ["fake"])
    monkeypatch.setattr("qdash.api.routers.task.is_task_available", lambda *_args: True)
    flow_service = SimpleNamespace(execute_single_task_from_snapshot=AsyncMock())

    with pytest.raises(HTTPException, match=message) as exc_info:
        await quick_run_task(
            task_name="CheckRabi",
            body=body,
            ctx=_project_context(),  # type: ignore[arg-type]
            flow_service=flow_service,  # type: ignore[arg-type]
            task_file_service=_task_file_service(_task_info()),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    flow_service.execute_single_task_from_snapshot.assert_not_awaited()
