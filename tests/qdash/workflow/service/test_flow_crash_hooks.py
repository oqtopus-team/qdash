"""Tests for the Prefect terminal hooks in calib_service (Issues #1270 / #1111).

When a flow run ends via cancellation, failure, or an infrastructure crash,
Prefect fires the corresponding ``on_*`` hook registered on the ``@flow``
decorator. These hooks run in a *separate* process, so they cannot access
in-memory state -- instead they read ``flow_run.parameters`` and close any
executions/tasks left open in MongoDB directly, via
``qdash.repository.execution_finalizer.finalize_executions_by_flow_run_id``.

These tests exercise the hook functions directly against an in-memory
MongoDB (mongomock via the ``init_db`` fixture).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.service.calib_service import (
    on_flow_cancellation,
    on_flow_crashed,
    on_flow_failure,
)

PROJECT_ID = "proj-1270"
FLOW_RUN_ID = "flow-run-1270"


def _make_execution(
    *,
    status: str,
    execution_id: str = "exec-1",
    flow_run_id: str = FLOW_RUN_ID,
    project_id: str = PROJECT_ID,
) -> ExecutionHistoryDocument:
    doc = ExecutionHistoryDocument(
        project_id=project_id,
        username="tester",
        name="test-flow",
        execution_id=execution_id,
        calib_data_path="/tmp/calib",
        note={"flow_run_id": flow_run_id},
        status=status,
        tags=["test"],
        chip_id="chip-1",
        message="",
        system_info=SystemInfoModel(),
    )
    doc.save()
    return doc


def _make_task(
    *,
    status: str,
    task_id: str,
    execution_id: str = "exec-1",
    project_id: str = PROJECT_ID,
) -> TaskResultHistoryDocument:
    doc = TaskResultHistoryDocument(
        project_id=project_id,
        username="tester",
        task_id=task_id,
        name="CheckRabi",
        upstream_id="",
        status=status,
        message="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        note={},
        figure_path=[],
        start_at=None,
        end_at=None,
        elapsed_time=None,
        task_type="qubit",
        system_info=SystemInfoModel(),
        execution_id=execution_id,
        tags=["test"],
        chip_id="chip-1",
    )
    doc.save()
    return doc


def _fake_flow_run(
    *, flow_run_id: str = FLOW_RUN_ID, project_id: str | None = PROJECT_ID
) -> SimpleNamespace:
    parameters = {"project_id": project_id} if project_id is not None else {}
    return SimpleNamespace(id=flow_run_id, parameters=parameters)


def _reload_execution(
    execution_id: str = "exec-1", project_id: str = PROJECT_ID
) -> ExecutionHistoryDocument | None:
    return ExecutionHistoryDocument.find_one(
        {"project_id": project_id, "execution_id": execution_id}
    ).run()


def _reload_task(task_id: str, project_id: str = PROJECT_ID) -> TaskResultHistoryDocument | None:
    return TaskResultHistoryDocument.find_one({"project_id": project_id, "task_id": task_id}).run()


def test_on_flow_crashed_closes_running_execution_and_open_tasks(init_db) -> None:
    """on_flow_crashed marks a running execution failed and closes its open tasks."""
    _make_execution(status="running")
    _make_task(status="running", task_id="task-running")
    _make_task(status="completed", task_id="task-completed")

    on_flow_crashed(None, _fake_flow_run(), None)

    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "failed"
    assert execution.end_at is not None

    running = _reload_task("task-running")
    assert running is not None
    assert running.status == "failed"
    assert running.end_at is not None

    completed = _reload_task("task-completed")
    assert completed is not None
    assert completed.status == "completed"


def test_on_flow_cancellation_closes_execution_as_cancelled(init_db) -> None:
    """on_flow_cancellation marks a running execution cancelled."""
    _make_execution(status="running")

    on_flow_cancellation(None, _fake_flow_run(), None)

    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "cancelled"


def test_on_flow_failure_closes_execution_as_failed(init_db) -> None:
    """on_flow_failure marks a running execution failed."""
    _make_execution(status="running")

    on_flow_failure(None, _fake_flow_run(), None)

    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "failed"


def test_hook_without_project_id_is_noop(init_db) -> None:
    """A flow_run whose parameters lack project_id leaves executions untouched."""
    _make_execution(status="running")

    on_flow_crashed(None, _fake_flow_run(project_id=None), None)

    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "running"


def test_hook_leaves_terminal_execution_untouched(init_db) -> None:
    """An execution that already reached a terminal status is not reopened."""
    _make_execution(status="completed")

    on_flow_crashed(None, _fake_flow_run(), None)

    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "completed"


def test_hook_swallows_finalizer_errors(init_db) -> None:
    """The hook never raises, even if the finalizer call blows up."""
    _make_execution(status="running")

    with patch(
        "qdash.repository.execution_finalizer.finalize_executions_by_flow_run_id",
        side_effect=RuntimeError("boom"),
    ):
        on_flow_crashed(None, _fake_flow_run(), None)

    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "running"
