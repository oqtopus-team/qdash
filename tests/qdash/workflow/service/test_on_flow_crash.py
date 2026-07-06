"""Tests for the on_flow_crash hook (Issue #1111).

When a flow subprocess is killed by an uncatchable signal (e.g. OOM SIGKILL),
Prefect marks the run CRASHED but the flow's own finalizers never run and the
``on_cancellation`` hook does not fire — so without ``on_flow_crash`` the
execution stays ``status: running`` / ``end_at: null`` forever.

These tests exercise the hook logic directly against an in-memory MongoDB
(mongomock via the ``init_db`` fixture). The full end-to-end firing of
``@flow(on_crashed=[on_flow_crash])`` through the real Prefect runner is covered
by the manual real-crash harness in ``yugo/issues/1111/repro/real_crash``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.workflow.service.calib_service import on_flow_crash

PROJECT_ID = "proj-1111"
FLOW_RUN_ID = "flow-run-1111"


def _make_execution(
    *,
    status: str,
    execution_id: str = "20260706-001",
    flow_run_id: str = FLOW_RUN_ID,
    project_id: str | None = PROJECT_ID,
    end_at: datetime | None = None,
) -> ExecutionHistoryDocument:
    doc = ExecutionHistoryDocument(
        project_id=project_id,
        username="tester",
        name="REPRO-1111",
        execution_id=execution_id,
        calib_data_path="/tmp/calib",
        note={"flow_run_id": flow_run_id},
        status=status,
        tags=["repro"],
        chip_id="64Q",
        message="",
        end_at=end_at,
        system_info=SystemInfoModel(),
    )
    doc.save()
    return doc


def _make_task(
    *,
    status: str,
    execution_id: str = "20260706-001",
    task_id: str = "task-1",
    project_id: str | None = PROJECT_ID,
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
        tags=["repro"],
        chip_id="64Q",
    )
    doc.save()
    return doc


def _fake_flow_run(flow_run_id: str = FLOW_RUN_ID, project_id: str | None = PROJECT_ID):
    params = {"project_id": project_id} if project_id is not None else {}
    return SimpleNamespace(id=flow_run_id, parameters=params)


def _reload(execution_id: str = "20260706-001") -> ExecutionHistoryDocument | None:
    return ExecutionHistoryDocument.find_one(
        {"project_id": PROJECT_ID, "execution_id": execution_id}
    ).run()


@pytest.mark.parametrize("status", ["running", "scheduled"])
def test_crash_finalizes_non_terminal_execution_to_failed(init_db, status):
    """A crashed running/scheduled execution is finalized to failed + end_at."""
    _make_execution(status=status)

    on_flow_crash(None, _fake_flow_run(), None)

    doc = _reload()
    assert doc is not None
    assert doc.status == "failed"
    assert doc.end_at is not None


def test_crash_finalizes_non_terminal_tasks_to_failed(init_db):
    """Non-terminal tasks of the crashed execution are marked failed + end_at."""
    _make_execution(status="running")
    _make_task(status="running", task_id="task-running")
    _make_task(status="pending", task_id="task-pending")
    _make_task(status="completed", task_id="task-done")

    on_flow_crash(None, _fake_flow_run(), None)

    running = TaskResultHistoryDocument.find_one(
        {"project_id": PROJECT_ID, "task_id": "task-running"}
    ).run()
    pending = TaskResultHistoryDocument.find_one(
        {"project_id": PROJECT_ID, "task_id": "task-pending"}
    ).run()
    done = TaskResultHistoryDocument.find_one(
        {"project_id": PROJECT_ID, "task_id": "task-done"}
    ).run()

    assert running is not None and running.status == "failed" and running.end_at is not None
    assert pending is not None and pending.status == "failed"
    # Already-terminal tasks are left untouched.
    assert done is not None and done.status == "completed"


def test_crash_releases_execution_lock(init_db):
    """The execution lock held by the crashed flow is released."""
    _make_execution(status="running")
    ExecutionLockDocument(project_id=PROJECT_ID, locked=True).save()

    on_flow_crash(None, _fake_flow_run(), None)

    lock = ExecutionLockDocument.find_one({"project_id": PROJECT_ID}).run()
    assert lock is not None
    assert lock.locked is False


def test_crash_does_not_clobber_already_cancelled_execution(init_db):
    """A cancel that already finalized the execution must not be overwritten.

    Cancellation sets status='cancelled' first; a later crash hook must leave it
    alone (it only targets running/scheduled), so cancel and crash never fight.
    """
    _make_execution(status="cancelled", end_at=datetime(2026, 7, 6, tzinfo=timezone.utc))

    on_flow_crash(None, _fake_flow_run(), None)

    doc = _reload()
    assert doc is not None
    assert doc.status == "cancelled"


def test_crash_leaves_completed_execution_untouched(init_db):
    """A completed execution is terminal and must not be reopened as failed."""
    _make_execution(status="completed", end_at=datetime(2026, 7, 6, tzinfo=timezone.utc))

    on_flow_crash(None, _fake_flow_run(), None)

    doc = _reload()
    assert doc is not None
    assert doc.status == "completed"


def test_crash_without_project_id_is_noop(init_db):
    """No project_id in flow_run parameters -> hook does nothing (and never raises)."""
    _make_execution(status="running")

    on_flow_crash(None, _fake_flow_run(project_id=None), None)

    doc = _reload()
    assert doc is not None
    assert doc.status == "running"
