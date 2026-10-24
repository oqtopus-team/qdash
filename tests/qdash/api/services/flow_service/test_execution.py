"""Tests for the execution coordinator."""

from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.services.flow_service import execution
from qdash.api.services.flow_service.execution import ExecutionCoordinator, FlowDispatchError
from qdash.common.execution_resources import ExecutionResourceScope
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel

if TYPE_CHECKING:
    from qdash.api.services.flow_service.prefect_gateway import PrefectGateway
    from qdash.repository import MongoExecutionLockRepository, MongoExecutionRepository


class _FakePrefect:
    """Prefect gateway stub that records dispatch and returns a fixed run ID."""

    def __init__(
        self,
        *,
        flow_run_id: str = "flow-run-1",
        failure: Exception | None = None,
        calls: list[str] | None = None,
    ) -> None:
        self.flow_run_id = flow_run_id
        self.failure = failure
        self.calls = calls if calls is not None else []
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def create_flow_run(self, *, deployment_id: Any, parameters: dict[str, Any]) -> str:
        """Record the dispatch and return the configured flow run ID."""
        self.calls.append("create_flow_run")
        if self.failure is not None:
            raise self.failure
        self.created.append({"deployment_id": deployment_id, "parameters": parameters})
        return self.flow_run_id

    async def read_deployment_id(self, deployment_name: str) -> Any:
        """Return a stub deployment ID."""
        self.calls.append("read_deployment_id")
        return "deployment-1"

    async def delete_deployment(self, deployment_id: str) -> None:
        """Record the deleted deployment."""
        self.deleted.append(deployment_id)


class _FakeLocks:
    """Execution lock stub with a configurable claim and conflict answer."""

    def __init__(
        self,
        *,
        acquires: bool = True,
        conflict: bool = False,
        calls: list[str] | None = None,
        unlock_failure: Exception | None = None,
    ) -> None:
        self.acquires = acquires
        self.conflict = conflict
        self.calls = calls if calls is not None else []
        self.unlock_failure = unlock_failure
        self.try_lock_kwargs: list[dict[str, Any]] = []
        self.unlocks: list[dict[str, Any]] = []
        self.scopes: list[ExecutionResourceScope] = []

    def try_lock(self, **kwargs: Any) -> bool:
        """Record the claim and answer with the configured result."""
        self.calls.append("try_lock")
        self.try_lock_kwargs.append(kwargs)
        return self.acquires

    def unlock(self, **kwargs: Any) -> None:
        """Record the release, raising when a failure is configured."""
        self.unlocks.append(kwargs)
        if self.unlock_failure is not None:
            raise self.unlock_failure

    def has_conflict(self, project_id: str, scope: ExecutionResourceScope) -> bool:
        """Record the inspected scope and answer with the configured result."""
        self.scopes.append(scope)
        return self.conflict


class _FakeExecutions:
    """Execution repository stub that records saved rows."""

    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.saved: list[ExecutionModel] = []

    def save(self, model: ExecutionModel) -> None:
        """Record the execution row, raising when a failure is configured."""
        if self.failure is not None:
            raise self.failure
        self.saved.append(model)


def _coordinator(
    *,
    locks: _FakeLocks | None = None,
    executions: _FakeExecutions | None = None,
    prefect: _FakePrefect | None = None,
    execution_id: str = "20240101-001",
) -> ExecutionCoordinator:
    """Build a coordinator with fakes and a deterministic execution ID."""
    return ExecutionCoordinator(
        lock_repository=cast("MongoExecutionLockRepository | None", locks),
        execution_repository=cast("MongoExecutionRepository", executions or _FakeExecutions()),
        prefect=cast("PrefectGateway", prefect or _FakePrefect()),
        id_factory=lambda *_args, **_kwargs: execution_id,
    )


async def _dispatch(
    coordinator: ExecutionCoordinator,
    *,
    chip_id: str = "chip-1",
    name: str = "my-flow",
    parameters: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    workflow: bool = False,
) -> Any:
    """Dispatch a run with the defaults used by the tests."""
    return await coordinator.dispatch_run(
        project_id="project-1",
        username="operator",
        chip_id=chip_id,
        name=name,
        deployment_id="deployment-1",
        parameters=parameters or {},
        tags=tags,
        workflow=workflow,
    )


@pytest.mark.asyncio
async def test_dispatch_claims_the_lock_before_creating_the_flow_run() -> None:
    """The lock is taken before Prefect is asked for a flow run, not after."""
    calls: list[str] = []
    locks = _FakeLocks(calls=calls)
    prefect = _FakePrefect(calls=calls)

    result = await _dispatch(_coordinator(locks=locks, prefect=prefect), workflow=True)

    assert calls == ["try_lock", "create_flow_run"]
    assert result.execution_id == "20240101-001"
    assert locks.unlocks == []
    assert locks.try_lock_kwargs == [
        {
            "project_id": "project-1",
            "execution_id": "20240101-001",
            "chip_id": "chip-1",
            "resources": (),
            "exclusive": True,
        }
    ]


@pytest.mark.asyncio
async def test_dispatch_rejects_when_another_run_holds_the_lock() -> None:
    """A concurrent dispatch that loses the race is rejected with 409."""
    locks = _FakeLocks(acquires=False)
    prefect = _FakePrefect()

    with pytest.raises(HTTPException) as exc_info:
        await _dispatch(_coordinator(locks=locks, prefect=prefect))

    assert exc_info.value.status_code == 409
    assert prefect.created == []
    assert locks.unlocks == []


@pytest.mark.asyncio
async def test_dispatch_releases_the_lock_when_the_flow_run_cannot_be_created() -> None:
    """A dispatch failure must not leave the project locked."""
    locks = _FakeLocks()
    prefect = _FakePrefect(failure=RuntimeError("prefect is down"))

    with pytest.raises(FlowDispatchError) as exc_info:
        await _dispatch(_coordinator(locks=locks, prefect=prefect))

    assert str(exc_info.value) == "prefect is down"
    assert locks.unlocks == [{"project_id": "project-1", "execution_id": "20240101-001"}]


@pytest.mark.asyncio
async def test_dispatch_keeps_the_dispatch_error_when_unlocking_fails() -> None:
    """A failing release is logged instead of replacing the dispatch error."""
    locks = _FakeLocks(unlock_failure=RuntimeError("mongo is down"))

    with pytest.raises(FlowDispatchError):
        await _dispatch(
            _coordinator(locks=locks, prefect=_FakePrefect(failure=RuntimeError("prefect is down")))
        )

    assert locks.unlocks == [{"project_id": "project-1", "execution_id": "20240101-001"}]


@pytest.mark.asyncio
async def test_dispatch_releases_the_lock_when_the_scheduled_row_cannot_be_saved() -> None:
    """Without a scheduled row the flow cannot adopt the lock, so it is released."""
    locks = _FakeLocks()
    executions = _FakeExecutions(failure=RuntimeError("mongo is down"))

    result = await _dispatch(_coordinator(locks=locks, executions=executions))

    assert result.execution_id is None
    assert result.flow_run_id == "flow-run-1"
    assert locks.unlocks == [{"project_id": "project-1", "execution_id": "20240101-001"}]


@pytest.mark.asyncio
async def test_dispatch_skips_the_claim_without_a_chip_id() -> None:
    """With no chip there is no execution ID to own the lock, so none is claimed."""
    locks = _FakeLocks()

    result = await _dispatch(_coordinator(locks=locks), chip_id="")

    assert locks.try_lock_kwargs == []
    assert locks.unlocks == []
    assert result.execution_id is None


@pytest.mark.asyncio
async def test_scheduled_row_records_the_flow_run_and_status() -> None:
    """The pre-created row links the flow run and starts as scheduled."""
    executions = _FakeExecutions()

    await _dispatch(_coordinator(executions=executions), name="my-flow", tags=["daily"])

    assert len(executions.saved) == 1
    row = executions.saved[0]
    assert row.execution_id == "20240101-001"
    assert row.name == "my-flow"
    assert row.chip_id == "chip-1"
    assert row.tags == ["daily"]
    assert row.note == {"flow_run_id": "flow-run-1"}
    assert row.status == ExecutionStatusModel.SCHEDULED


@pytest.mark.asyncio
async def test_workflow_dispatch_reserves_the_whole_chip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workflow run claims the chip exclusively, ignoring target overrides."""
    whole_chip = ExecutionResourceScope("chip-1", (), True)
    scoped = ExecutionResourceScope("chip-1", ("mux:0",), False)
    monkeypatch.setattr(execution, "resolve_workflow_resource_scope", lambda _chip_id: whole_chip)
    monkeypatch.setattr(execution, "resolve_execution_resource_scope", lambda *_args: scoped)
    locks = _FakeLocks()

    await _dispatch(
        _coordinator(locks=locks),
        parameters={"mux_ids": [1]},
        workflow=True,
    )

    assert locks.try_lock_kwargs[0]["resources"] == ()
    assert locks.try_lock_kwargs[0]["exclusive"] is True


@pytest.mark.asyncio
async def test_single_task_dispatch_stays_scoped_to_its_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-task run claims only the hardware its parameters select."""
    scoped = ExecutionResourceScope("chip-1", ("mux:0",), False)
    monkeypatch.setattr(execution, "resolve_execution_resource_scope", lambda *_args: scoped)
    locks = _FakeLocks()

    await _dispatch(_coordinator(locks=locks), parameters={"qid": "0"}, workflow=False)

    assert locks.try_lock_kwargs == [
        {
            "project_id": "project-1",
            "execution_id": "20240101-001",
            "chip_id": "chip-1",
            "resources": ("mux:0",),
            "exclusive": False,
        }
    ]


@pytest.mark.parametrize(
    ("workflow", "expected_fragment"),
    [(True, "entire chip"), (False, "hardware required by this run")],
)
def test_availability_explains_the_conflict_for_the_run_kind(
    monkeypatch: pytest.MonkeyPatch,
    workflow: bool,
    expected_fragment: str,
) -> None:
    """The refusal reason describes the scope the run would have claimed."""
    scope = ExecutionResourceScope("chip-1", (), workflow)
    monkeypatch.setattr(execution, "resolve_workflow_resource_scope", lambda _chip_id: scope)
    monkeypatch.setattr(execution, "resolve_execution_resource_scope", lambda *_args: scope)
    locks = _FakeLocks(conflict=True)

    available, reason = _coordinator(locks=locks).availability(
        project_id="project-1",
        chip_id="chip-1",
        parameters={},
        workflow=workflow,
    )

    assert available is False
    assert reason is not None and expected_fragment in reason
    assert locks.scopes == [scope]
    assert locks.try_lock_kwargs == []


def test_availability_reports_unavailable_locking() -> None:
    """Availability cannot be answered without a lock repository."""
    with pytest.raises(HTTPException) as exc_info:
        _coordinator().availability(
            project_id="project-1",
            chip_id="chip-1",
            parameters={},
            workflow=True,
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_background_dispatch_owns_no_lock_or_execution_row() -> None:
    """The agent candidate apply path dispatches without touching execution state."""
    locks = _FakeLocks()
    executions = _FakeExecutions()

    flow_run_id = await _coordinator(locks=locks, executions=executions).dispatch_background(
        deployment_id="deployment-1",
        parameters={"session_id": "session-1"},
    )

    assert flow_run_id == "flow-run-1"
    assert locks.try_lock_kwargs == []
    assert locks.unlocks == []
    assert executions.saved == []
