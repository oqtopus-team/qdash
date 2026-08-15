"""Tests for ExecutionService Prefect reconciliation of stuck executions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import qdash.api.services.execution_service as execution_service
from qdash.api.services.execution_service import ExecutionService
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.execution_history import MongoExecutionHistoryRepository
from qdash.repository.execution_lock import MongoExecutionLockRepository

PROJECT_ID = "proj-1"
CHIP_ID = "chip-1"


def _make_service() -> ExecutionService:
    return ExecutionService(
        execution_history_repository=MongoExecutionHistoryRepository(),
        execution_lock_repository=MongoExecutionLockRepository(),
    )


def _make_execution(
    *,
    execution_id: str,
    status: str,
    note: dict[str, Any] | None = None,
    project_id: str = PROJECT_ID,
    chip_id: str = CHIP_ID,
) -> ExecutionHistoryDocument:
    doc = ExecutionHistoryDocument(
        project_id=project_id,
        username="tester",
        name="test-flow",
        execution_id=execution_id,
        calib_data_path="/tmp/calib",
        note=note if note is not None else {},
        status=status,
        tags=["test"],
        chip_id=chip_id,
        message="",
        system_info=SystemInfoModel(),
    )
    doc.save()
    return doc


def _make_task(
    *,
    task_id: str,
    execution_id: str,
    status: str,
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
        chip_id=CHIP_ID,
    )
    doc.save()
    return doc


def _reload_execution(
    execution_id: str, project_id: str = PROJECT_ID
) -> ExecutionHistoryDocument | None:
    return ExecutionHistoryDocument.find_one(
        {"project_id": project_id, "execution_id": execution_id}
    ).run()


def _reload_task(task_id: str, project_id: str = PROJECT_ID) -> TaskResultHistoryDocument | None:
    return TaskResultHistoryDocument.find_one({"project_id": project_id, "task_id": task_id}).run()


def _make_run(flow_run_id: str, state_type: str | None) -> SimpleNamespace:
    state = SimpleNamespace(type=SimpleNamespace(value=state_type)) if state_type else None
    return SimpleNamespace(id=UUID(flow_run_id), state=state)


class _FakeSyncClient:
    def __init__(self, runs: list[SimpleNamespace]) -> None:
        self._runs = runs
        self.calls: list[dict[str, Any]] = []

    def read_flow_runs(self, **kwargs: Any) -> list[SimpleNamespace]:
        self.calls.append(kwargs)
        return self._runs


class _RaisingSyncClient:
    def read_flow_runs(self, **kwargs: Any) -> list[SimpleNamespace]:
        raise RuntimeError("prefect unavailable")


class _FakeSyncClientContext:
    def __init__(self, client: Any) -> None:
        self._client = client

    def __enter__(self) -> Any:
        return self._client

    def __exit__(self, *args: Any) -> None:
        return None


def _make_get_client(client: Any, calls: list[dict[str, Any]]) -> Any:
    def _get_client(**kwargs: Any) -> _FakeSyncClientContext:
        calls.append(kwargs)
        return _FakeSyncClientContext(client)

    return _get_client


def test_list_executions_closes_running_execution_on_failed_flow_run(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})
    _make_task(task_id="task-1", execution_id="exec-1", status="running")

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "FAILED")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert len(call_count) == 1
    assert call_count[0]["sync_client"] is True
    assert call_count[0]["httpx_settings"] == {
        "timeout": execution_service._RECONCILE_TIMEOUT_SECONDS
    }
    assert len(executions) == 1
    assert executions[0].status == "failed"

    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "failed"
    assert reloaded.end_at is not None

    task = _reload_task("task-1")
    assert task is not None
    assert task.status == "failed"


def test_list_executions_closes_running_execution_on_crashed_flow_run(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})
    _make_task(task_id="task-1", execution_id="exec-1", status="running")

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "CRASHED")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert executions[0].status == "failed"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "failed"

    task = _reload_task("task-1")
    assert task is not None
    assert task.status == "failed"


def test_list_executions_closes_running_execution_on_cancelled_flow_run(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})
    _make_task(task_id="task-1", execution_id="exec-1", status="running")

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "CANCELLED")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert executions[0].status == "cancelled"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "cancelled"

    task = _reload_task("task-1")
    assert task is not None
    assert task.status == "cancelled"


def test_list_executions_completes_scheduled_execution_without_closing_its_tasks(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="scheduled", note={"flow_run_id": flow_run_id})
    _make_task(task_id="task-1", execution_id="exec-1", status="running")

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "COMPLETED")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert executions[0].status == "completed"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "completed"

    task = _reload_task("task-1")
    assert task is not None
    assert task.status == "running"


def test_list_executions_fails_running_execution_on_completed_flow_run(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})
    _make_task(task_id="task-1", execution_id="exec-1", status="running")

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "COMPLETED")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert executions[0].status == "failed"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "failed"

    task = _reload_task("task-1")
    assert task is not None
    assert task.status == "failed"


def test_list_executions_leaves_execution_untouched_when_flow_run_still_running(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "RUNNING")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert executions[0].status == "running"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "running"
    assert reloaded.end_at is None


def test_list_executions_leaves_execution_untouched_when_prefect_omits_flow_run(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert len(call_count) == 1
    assert executions[0].status == "running"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "running"


def test_list_executions_skips_prefect_when_no_open_executions(
    monkeypatch: Any, init_db: Any
) -> None:
    _make_execution(execution_id="exec-1", status="completed", note={})

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert call_count == []
    assert executions[0].status == "completed"


def test_list_executions_skips_executions_with_missing_or_invalid_flow_run_id(
    monkeypatch: Any, init_db: Any
) -> None:
    _make_execution(execution_id="exec-missing-note", status="running", note={})
    _make_execution(
        execution_id="exec-bad-uuid", status="running", note={"flow_run_id": "not-a-uuid"}
    )

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    _make_service().list_executions(project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20)

    assert call_count == []
    missing_note = _reload_execution("exec-missing-note")
    bad_uuid = _reload_execution("exec-bad-uuid")
    assert missing_note is not None
    assert missing_note.status == "running"
    assert bad_uuid is not None
    assert bad_uuid.status == "running"


def test_list_executions_returns_unreconciled_summaries_when_prefect_raises(
    monkeypatch: Any, init_db: Any
) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})

    call_count: list[dict[str, Any]] = []
    monkeypatch.setattr(
        execution_service, "get_client", _make_get_client(_RaisingSyncClient(), call_count)
    )

    executions = _make_service().list_executions(
        project_id=PROJECT_ID, chip_id=CHIP_ID, skip=0, limit=20
    )

    assert len(call_count) == 1
    assert executions[0].status == "running"
    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "running"


def test_get_execution_reconciles_crashed_flow_run(monkeypatch: Any, init_db: Any) -> None:
    flow_run_id = str(uuid4())
    _make_execution(execution_id="exec-1", status="running", note={"flow_run_id": flow_run_id})
    _make_task(task_id="task-1", execution_id="exec-1", status="running")

    call_count: list[dict[str, Any]] = []
    client = _FakeSyncClient([_make_run(flow_run_id, "CRASHED")])
    monkeypatch.setattr(execution_service, "get_client", _make_get_client(client, call_count))

    detail = _make_service().get_execution(project_id=PROJECT_ID, execution_id="exec-1")

    assert detail is not None
    assert detail.status == "failed"
    assert len(detail.task) == 1
    assert detail.task[0].status == "failed"

    reloaded = _reload_execution("exec-1")
    assert reloaded is not None
    assert reloaded.status == "failed"
