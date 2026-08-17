"""Tests for finalize_executions_by_flow_run_id."""

from __future__ import annotations

from unittest.mock import patch

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.execution_finalizer import finalize_executions_by_flow_run_id

PROJECT_ID = "proj-1"
FLOW_RUN_ID = "flow-run-1"


def _make_execution(
    *,
    status: str,
    execution_id: str = "exec-1",
    flow_run_id: str | None = FLOW_RUN_ID,
    project_id: str | None = PROJECT_ID,
) -> ExecutionHistoryDocument:
    """Create and save an ExecutionHistoryDocument fixture with the given status."""
    note = {"flow_run_id": flow_run_id} if flow_run_id is not None else {}
    doc = ExecutionHistoryDocument(
        project_id=project_id,
        username="tester",
        name="test-flow",
        execution_id=execution_id,
        calib_data_path="/tmp/calib",
        note=note,
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
    project_id: str | None = PROJECT_ID,
) -> TaskResultHistoryDocument:
    """Create and save a TaskResultHistoryDocument fixture with the given status."""
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


def _reload_execution(
    execution_id: str = "exec-1", project_id: str = PROJECT_ID
) -> ExecutionHistoryDocument | None:
    """Reload the execution document with the given execution_id from the database."""
    return ExecutionHistoryDocument.find_one(
        {"project_id": project_id, "execution_id": execution_id}
    ).run()


def _reload_task(task_id: str, project_id: str = PROJECT_ID) -> TaskResultHistoryDocument | None:
    """Reload the task document with the given task_id from the database."""
    return TaskResultHistoryDocument.find_one({"project_id": project_id, "task_id": task_id}).run()


def test_closes_running_execution_and_open_tasks(init_db) -> None:
    """A running execution matching flow_run_id is closed with its open tasks."""
    _make_execution(status="running")
    _make_task(status="running", task_id="task-running")
    _make_task(status="scheduled", task_id="task-scheduled")
    _make_task(status="pending", task_id="task-pending")
    _make_task(status="completed", task_id="task-completed")

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
    )

    assert closed == ["exec-1"]
    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "failed"
    assert execution.end_at is not None
    assert execution.message == "boom"

    for task_id in ("task-running", "task-scheduled", "task-pending"):
        task = _reload_task(task_id)
        assert task is not None
        assert task.status == "failed"
        assert task.message == "boom"
        assert task.end_at is not None

    completed = _reload_task("task-completed")
    assert completed is not None
    assert completed.status == "completed"


def test_ignores_execution_from_different_project(init_db) -> None:
    """An execution with the same flow_run_id in a different project is untouched."""
    _make_execution(status="running", project_id="other-project")

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
    )

    assert closed == []
    execution = _reload_execution(project_id="other-project")
    assert execution is not None
    assert execution.status == "running"


def test_ignores_execution_with_different_flow_run_id(init_db) -> None:
    """An execution with a different flow_run_id is untouched."""
    _make_execution(status="running", flow_run_id="other-flow-run")

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
    )

    assert closed == []
    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "running"


def test_ignores_already_terminal_execution(init_db) -> None:
    """A completed execution is not in the default from_statuses and is left alone."""
    _make_execution(status="completed")

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
    )

    assert closed == []
    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "completed"


def test_from_statuses_restricts_which_executions_close(init_db) -> None:
    """from_statuses=("scheduled",) only closes the scheduled execution."""
    _make_execution(status="scheduled", execution_id="exec-scheduled")
    _make_execution(status="running", execution_id="exec-running")

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
        from_statuses=("scheduled",),
    )

    assert closed == ["exec-scheduled"]
    scheduled = _reload_execution(execution_id="exec-scheduled")
    running = _reload_execution(execution_id="exec-running")
    assert scheduled is not None
    assert scheduled.status == "failed"
    assert running is not None
    assert running.status == "running"


def test_close_tasks_false_leaves_tasks_untouched(init_db) -> None:
    """close_tasks=False still closes the execution but leaves its tasks alone."""
    _make_execution(status="running")
    _make_task(status="running", task_id="task-running")

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
        close_tasks=False,
    )

    assert closed == ["exec-1"]
    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "failed"

    task = _reload_task("task-running")
    assert task is not None
    assert task.status == "running"


def test_release_lock_true_unlocks_unowned_project(init_db) -> None:
    """release_lock=True flips a locked-but-unowned ExecutionLockDocument to unlocked."""
    _make_execution(status="running")
    ExecutionLockDocument(project_id=PROJECT_ID, locked=True).save()

    finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
        release_lock=True,
    )

    lock = ExecutionLockDocument.find_one({"project_id": PROJECT_ID}).run()
    assert lock is not None
    assert lock.locked is False
    assert lock.execution_id is None


def test_release_lock_owned_by_closed_execution_unlocks_project(init_db) -> None:
    """A lock owned by the execution being closed is released."""
    _make_execution(status="running", execution_id="exec-1")
    ExecutionLockDocument(project_id=PROJECT_ID, locked=True, execution_id="exec-1").save()

    finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
        release_lock=True,
    )

    lock = ExecutionLockDocument.find_one({"project_id": PROJECT_ID}).run()
    assert lock is not None
    assert lock.locked is False
    assert lock.execution_id is None


def test_release_lock_owned_by_other_execution_stays_locked(init_db) -> None:
    """A lock owned by a different, still-running execution is not released.

    Regression test for the finding where a delayed finalizer for one
    execution could clear the lock of a newer, unrelated execution that had
    since acquired it.
    """
    _make_execution(status="running", execution_id="exec-1")
    ExecutionLockDocument(project_id=PROJECT_ID, locked=True, execution_id="exec-other").save()

    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
        release_lock=True,
    )

    assert closed == ["exec-1"]
    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "failed"

    lock = ExecutionLockDocument.find_one({"project_id": PROJECT_ID}).run()
    assert lock is not None
    assert lock.locked is True
    assert lock.execution_id == "exec-other"


def test_release_lock_false_leaves_lock_untouched(init_db) -> None:
    """release_lock=False leaves an existing lock in place."""
    _make_execution(status="running")
    ExecutionLockDocument(project_id=PROJECT_ID, locked=True).save()

    finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
        release_lock=False,
    )

    lock = ExecutionLockDocument.find_one({"project_id": PROJECT_ID}).run()
    assert lock is not None
    assert lock.locked is True


def test_returns_empty_list_when_nothing_matches(init_db) -> None:
    """Returns [] when there is nothing to close."""
    closed = finalize_executions_by_flow_run_id(
        project_id=PROJECT_ID,
        flow_run_id=FLOW_RUN_ID,
        status="failed",
        message="boom",
    )

    assert closed == []


def test_release_lock_swallows_lookup_failure(init_db) -> None:
    """A lock lookup failure is logged and swallowed, not raised."""
    _make_execution(status="running")

    with patch(
        "qdash.repository.execution_finalizer.ExecutionLockDocument.find_one",
        side_effect=RuntimeError("boom"),
    ):
        closed = finalize_executions_by_flow_run_id(
            project_id=PROJECT_ID,
            flow_run_id=FLOW_RUN_ID,
            status="failed",
            message="boom",
            release_lock=True,
        )

    assert closed == ["exec-1"]
    execution = _reload_execution()
    assert execution is not None
    assert execution.status == "failed"
