"""Tests for the flow application service."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi import HTTPException

from qdash.api.schemas.execution import ExecutionAvailabilityRequest
from qdash.api.schemas.flow import ExecuteFlowRequest, SaveFlowRequest
from qdash.api.services.flow_service import service as flow_service_module
from qdash.api.services.flow_service.deployment_client import DeploymentRegistrationError
from qdash.api.services.flow_service.execution import DispatchResult, FlowDispatchError
from qdash.api.services.flow_service.prefect_gateway import SystemDeploymentUnavailable
from qdash.api.services.flow_service.service import FlowService
from qdash.api.services.flow_service.source_store import FlowSourceStore

if TYPE_CHECKING:
    from qdash.api.services.flow_service.deployment_client import DeploymentServiceClient
    from qdash.api.services.flow_service.execution import ExecutionCoordinator
    from qdash.repository import MongoFlowRepository

FLOW_CODE = "from prefect import flow\n\n\n@flow\ndef my_flow():\n    pass\n"
TIMESTAMP = datetime(2024, 1, 1, tzinfo=timezone.utc)


class _FakeFlowRepository:
    """Flow repository stub that records writes."""

    def __init__(self, *, flow: SimpleNamespace | None = None) -> None:
        self.flow = flow
        self.listed: list[SimpleNamespace] = []
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.deleted: list[tuple[str, str]] = []
        self.create_failure: Exception | None = None
        self.delete_failure: Exception | None = None
        self.update_failure: Exception | None = None
        self.list_failure: Exception | None = None

    def find_by_project_and_name(self, project_id: str, name: str) -> SimpleNamespace | None:
        """Return the configured flow."""
        return self.flow

    def list_by_project(self, project_id: str) -> list[SimpleNamespace]:
        """Return the configured flow list, raising when a failure is configured."""
        if self.list_failure is not None:
            raise self.list_failure
        return self.listed

    def create_flow(self, **kwargs: Any) -> None:
        """Record the created flow, raising when a failure is configured."""
        if self.create_failure is not None:
            raise self.create_failure
        self.created.append(kwargs)

    def update_flow(self, flow: Any = None, **kwargs: Any) -> None:
        """Record the updated fields, raising when a failure is configured."""
        if self.update_failure is not None:
            raise self.update_failure
        self.updated.append({"flow": flow, **kwargs})

    def delete_by_project_and_name(self, project_id: str, name: str) -> None:
        """Record the deletion, raising when a failure is configured."""
        if self.delete_failure is not None:
            raise self.delete_failure
        self.deleted.append((project_id, name))


class _StubCoordinator:
    """Execution coordinator stub with configurable results."""

    def __init__(
        self,
        *,
        execution_id: str | None = "exec-1",
        flow_run_id: str = "flow-run-1",
        dispatch_failure: Exception | None = None,
        background_failure: Exception | None = None,
        unavailable: bool = False,
        available: tuple[bool, str | None] = (True, None),
    ) -> None:
        self.execution_id = execution_id
        self.flow_run_id = flow_run_id
        self.dispatch_failure = dispatch_failure
        self.background_failure = background_failure
        self.unavailable = unavailable
        self.available = available
        self.run_calls: list[dict[str, Any]] = []
        self.background_calls: list[dict[str, Any]] = []
        self.availability_calls: list[dict[str, Any]] = []
        self.deleted_deployments: list[str] = []

    async def dispatch_run(self, **kwargs: Any) -> DispatchResult:
        """Record the dispatch and return a result built from the request."""
        self.run_calls.append(kwargs)
        if self.dispatch_failure is not None:
            raise self.dispatch_failure
        chip_id = cast("str", kwargs["chip_id"])
        return DispatchResult(
            flow_run_id=self.flow_run_id,
            flow_run_url=f"http://localhost:4200/runs/flow-run/{self.flow_run_id}",
            execution_id=self.execution_id,
            qdash_ui_url=_ui_url(chip_id, self.execution_id),
        )

    async def dispatch_background(self, **kwargs: Any) -> str:
        """Record the background dispatch and return the configured run ID."""
        self.background_calls.append(kwargs)
        if self.background_failure is not None:
            raise self.background_failure
        return self.flow_run_id

    async def read_deployment_id(self, deployment_name: str) -> Any:
        """Return a stub deployment ID or report it as unavailable."""
        if self.unavailable:
            raise SystemDeploymentUnavailable(deployment_name)
        return "deployment-1"

    async def delete_deployment(self, deployment_id: str) -> None:
        """Record the deleted deployment."""
        self.deleted_deployments.append(deployment_id)

    def availability(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Record the availability question and return the configured answer."""
        self.availability_calls.append(kwargs)
        return self.available


class _StubDeploymentClient:
    """Deployment client stub that records registrations."""

    def __init__(
        self,
        *,
        deployment_id: str = "deployment-9",
        failure: Exception | None = None,
    ) -> None:
        self.deployment_id = deployment_id
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    async def register(self, **kwargs: Any) -> str:
        """Record the registration and return the configured deployment ID."""
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return self.deployment_id


def _ui_url(chip_id: str | None, execution_id: str | None) -> str:
    """Mirror the QDash UI URL the coordinator builds."""
    base = "http://localhost:3000/execution"
    if not chip_id:
        return base
    if not execution_id:
        return f"{base}/{chip_id}"
    return f"{base}/{chip_id}/{execution_id}"


def _make_flow(file_path: Path, **overrides: Any) -> SimpleNamespace:
    """Build a flow record with the fields the service reads."""
    values: dict[str, Any] = {
        "name": "my_flow",
        "username": "operator",
        "description": "",
        "chip_id": "chip-1",
        "flow_function_name": "my_flow",
        "default_parameters": {},
        "default_run_parameters": {},
        "file_path": str(file_path),
        "deployment_id": "deployment-1",
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        "tags": [],
        "folder": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service(
    tmp_path: Path,
    *,
    repo: _FakeFlowRepository | None = None,
    coordinator: _StubCoordinator | None = None,
    deployment: _StubDeploymentClient | None = None,
) -> FlowService:
    """Build a service with fakes and a temporary flow tree."""
    return FlowService(
        flow_repository=cast("MongoFlowRepository", repo or _FakeFlowRepository()),
        coordinator=cast("ExecutionCoordinator", coordinator or _StubCoordinator()),
        source_store=FlowSourceStore(tmp_path / "user_flows"),
        deployment_client=cast(
            "DeploymentServiceClient",
            deployment or _StubDeploymentClient(),
        ),
    )


@pytest.mark.asyncio
async def test_save_flow_writes_the_source_and_registers_the_deployment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saving writes the file, registers the deployment and records metadata."""
    monkeypatch.setattr(flow_service_module, "format_with_ruff", lambda _path: None)
    repo = _FakeFlowRepository()
    deployment = _StubDeploymentClient()
    service = _service(tmp_path, repo=repo, deployment=deployment)

    response = await service.save_flow(
        SaveFlowRequest(name="my_flow", code=FLOW_CODE, chip_id="chip-1"),
        "operator",
        "project-1",
    )

    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    assert file_path.read_text(encoding="utf-8") == FLOW_CODE
    assert Path(deployment.calls[0]["file_path"]) == Path(
        "/app/qdash/workflow/user_flows/project-1/my_flow.py"
    )
    assert deployment.calls[0]["flow_function_name"] == "my_flow"
    assert deployment.calls[0]["deployment_name"] == "project-1-my_flow"
    assert deployment.calls[0]["old_deployment_id"] is None
    assert repo.created[0]["deployment_id"] == "deployment-9"
    assert repo.created[0]["folder"] == ""
    assert repo.created[0]["flow_function_name"] == "my_flow"
    assert response.file_path == str(file_path)
    assert response.message == "Flow 'my_flow' created successfully"


@pytest.mark.asyncio
async def test_save_flow_keeps_the_stored_folder_when_the_request_omits_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An omitted folder leaves the existing folder and replaces the deployment."""
    monkeypatch.setattr(flow_service_module, "format_with_ruff", lambda _path: None)
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    repo = _FakeFlowRepository(flow=_make_flow(file_path, folder="daily"))
    service = _service(tmp_path, repo=repo)

    response = await service.save_flow(
        SaveFlowRequest(name="my_flow", code=FLOW_CODE, chip_id="chip-1", description="updated"),
        "operator",
        "project-1",
    )

    assert repo.created == []
    assert repo.updated[0]["folder"] is None
    assert repo.updated[0]["description"] == "updated"
    assert response.message == "Flow 'my_flow' updated successfully"


@pytest.mark.asyncio
async def test_save_flow_removes_the_file_when_registration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed registration does not leave the new source behind."""
    monkeypatch.setattr(flow_service_module, "format_with_ruff", lambda _path: None)
    service = _service(
        tmp_path,
        deployment=_StubDeploymentClient(
            failure=DeploymentRegistrationError("500: worker is down")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.save_flow(
            SaveFlowRequest(name="my_flow", code=FLOW_CODE, chip_id="chip-1"),
            "operator",
            "project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to register deployment: 500: worker is down"
    assert not (tmp_path / "user_flows" / "project-1" / "my_flow.py").exists()


@pytest.mark.asyncio
async def test_save_flow_removes_the_file_when_metadata_cannot_be_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed metadata write does not leave the new source behind."""
    monkeypatch.setattr(flow_service_module, "format_with_ruff", lambda _path: None)
    repo = _FakeFlowRepository()
    repo.create_failure = RuntimeError("mongo is down")
    service = _service(tmp_path, repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.save_flow(
            SaveFlowRequest(name="my_flow", code=FLOW_CODE, chip_id="chip-1"),
            "operator",
            "project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save flow metadata: mongo is down"
    assert not (tmp_path / "user_flows" / "project-1" / "my_flow.py").exists()


@pytest.mark.asyncio
async def test_save_flow_rejects_an_invalid_name_before_touching_storage(
    tmp_path: Path,
) -> None:
    """A rejected name never reaches the filesystem or the repository."""
    repo = _FakeFlowRepository()
    service = _service(tmp_path, repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.save_flow(
            SaveFlowRequest(name="my flow", code=FLOW_CODE, chip_id="chip-1"),
            "operator",
            "project-1",
        )

    assert exc_info.value.status_code == 400
    assert repo.created == []
    assert not (tmp_path / "user_flows" / "project-1").exists()


@pytest.mark.asyncio
async def test_get_flow_returns_the_stored_source(tmp_path: Path) -> None:
    """Reading a flow returns its metadata and code."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(FLOW_CODE, encoding="utf-8")
    service = _service(
        tmp_path,
        repo=_FakeFlowRepository(flow=_make_flow(file_path, description="daily run")),
    )

    response = await service.get_flow("my_flow", "operator", "project-1")

    assert response.code == FLOW_CODE
    assert response.description == "daily run"
    assert response.file_path == str(file_path)


@pytest.mark.asyncio
async def test_get_flow_rejects_an_unknown_flow(tmp_path: Path) -> None:
    """A flow without metadata is reported as not found."""
    with pytest.raises(HTTPException) as exc_info:
        await _service(tmp_path).get_flow("missing", "operator", "project-1")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_flow_rejects_a_missing_source_file(tmp_path: Path) -> None:
    """Metadata whose file disappeared is reported as not found."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    service = _service(tmp_path, repo=_FakeFlowRepository(flow=_make_flow(file_path)))

    with pytest.raises(HTTPException) as exc_info:
        await service.get_flow("my_flow", "operator", "project-1")

    assert exc_info.value.status_code == 404
    assert "Flow file not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_move_flow_records_the_normalized_folder(tmp_path: Path) -> None:
    """Moving a flow rewrites its folder and nothing else."""
    repo = _FakeFlowRepository(flow=_make_flow(Path("/tmp/my_flow.py")))
    service = _service(tmp_path, repo=repo)

    response = await service.move_flow("my_flow", "project-1", "/daily/t1/")

    assert repo.updated == [{"flow": repo.flow, "folder": "daily/t1"}]
    assert response.folder == "daily/t1"
    assert response.message == "Flow 'my_flow' moved to 'daily/t1'"


@pytest.mark.asyncio
async def test_move_flow_rejects_an_unknown_flow(tmp_path: Path) -> None:
    """Moving a flow that does not exist is reported as not found."""
    with pytest.raises(HTTPException) as exc_info:
        await _service(tmp_path).move_flow("missing", "project-1", "daily")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_flows_reports_whether_each_file_exists(tmp_path: Path) -> None:
    """A summary flags flows whose source is gone."""
    present = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    present.parent.mkdir(parents=True)
    present.write_text(FLOW_CODE, encoding="utf-8")
    repo = _FakeFlowRepository()
    repo.listed = [
        _make_flow(present),
        _make_flow(present.with_name("gone.py"), name="gone"),
    ]
    service = _service(tmp_path, repo=repo)

    response = await service.list_flows("operator", "project-1")

    assert [summary.file_exists for summary in response.flows] == [True, False]


@pytest.mark.asyncio
async def test_list_flows_reports_a_repository_failure(tmp_path: Path) -> None:
    """A failing flow list is reported as a server error."""
    repo = _FakeFlowRepository()
    repo.list_failure = RuntimeError("mongo is down")

    with pytest.raises(HTTPException) as exc_info:
        await _service(tmp_path, repo=repo).list_flows("operator", "project-1")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to list flows: mongo is down"


@pytest.mark.asyncio
async def test_delete_flow_drops_the_deployment_file_and_metadata(tmp_path: Path) -> None:
    """Deleting removes the deployment, the source and the metadata."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(FLOW_CODE, encoding="utf-8")
    repo = _FakeFlowRepository(flow=_make_flow(file_path))
    coordinator = _StubCoordinator()
    service = _service(tmp_path, repo=repo, coordinator=coordinator)

    response = await service.delete_flow("my_flow", "operator", "project-1")

    assert coordinator.deleted_deployments == ["deployment-1"]
    assert not file_path.exists()
    assert repo.deleted == [("project-1", "my_flow")]
    assert response["message"] == "Flow 'my_flow' deleted successfully"


@pytest.mark.asyncio
async def test_delete_flow_reports_a_metadata_failure(tmp_path: Path) -> None:
    """A failed metadata delete is reported after the file is removed."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(FLOW_CODE, encoding="utf-8")
    repo = _FakeFlowRepository(flow=_make_flow(file_path))
    repo.delete_failure = RuntimeError("mongo is down")
    service = _service(tmp_path, repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_flow("my_flow", "operator", "project-1")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to delete flow metadata: mongo is down"


@pytest.mark.asyncio
async def test_delete_flow_rejects_an_unknown_flow(tmp_path: Path) -> None:
    """Deleting a flow that does not exist is reported as not found."""
    with pytest.raises(HTTPException) as exc_info:
        await _service(tmp_path).delete_flow("missing", "operator", "project-1")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_flow_skips_an_absent_deployment_and_file(tmp_path: Path) -> None:
    """Metadata without a deployment or a file on disk is still deleted."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    repo = _FakeFlowRepository(flow=_make_flow(file_path, deployment_id=""))
    coordinator = _StubCoordinator()
    service = _service(tmp_path, repo=repo, coordinator=coordinator)

    response = await service.delete_flow("my_flow", "operator", "project-1")

    assert coordinator.deleted_deployments == []
    assert repo.deleted == [("project-1", "my_flow")]
    assert response["message"] == "Flow 'my_flow' deleted successfully"


@pytest.mark.asyncio
async def test_execute_flow_merges_defaults_and_request_parameters(tmp_path: Path) -> None:
    """Execution combines saved defaults, request parameters and identity."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    repo = _FakeFlowRepository(
        flow=_make_flow(
            file_path,
            default_parameters={"qids": ["0"]},
            tags=["daily"],
        )
    )
    coordinator = _StubCoordinator()
    service = _service(tmp_path, repo=repo, coordinator=coordinator)

    response = await service.execute_flow(
        name="my_flow",
        request=ExecuteFlowRequest(parameters={"qid": "1"}),
        username="operator",
        project_id="project-1",
    )

    call = coordinator.run_calls[0]
    assert call["parameters"] == {
        "qids": ["0"],
        "qid": "1",
        "tags": ["daily"],
        "username": "operator",
        "flow_name": "my_flow",
        "project_id": "project-1",
    }
    assert call["tags"] == ["daily"]
    assert call["workflow"] is True
    assert call["deployment_id"] == "deployment-1"
    assert response.execution_id == "exec-1"
    assert response.flow_run_id == "flow-run-1"
    assert response.qdash_ui_url.endswith("/execution/chip-1/exec-1")


@pytest.mark.asyncio
async def test_execute_flow_falls_back_to_the_flow_run_id(tmp_path: Path) -> None:
    """Without a pre-created execution row the flow run ID is returned."""
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    repo = _FakeFlowRepository(flow=_make_flow(file_path, chip_id=""))
    service = _service(
        tmp_path,
        repo=repo,
        coordinator=_StubCoordinator(execution_id=None, flow_run_id="flow-run-4"),
    )

    response = await service.execute_flow(
        name="my_flow",
        request=ExecuteFlowRequest(parameters={}),
        username="operator",
        project_id="project-1",
    )

    assert response.execution_id == "flow-run-4"
    assert response.qdash_ui_url.endswith("/execution")


@pytest.mark.asyncio
async def test_execute_flow_requires_a_registered_deployment(tmp_path: Path) -> None:
    """A flow saved before deployment registration cannot run."""
    repo = _FakeFlowRepository(flow=_make_flow(Path("/tmp/my_flow.py"), deployment_id=""))
    service = _service(tmp_path, repo=repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_flow(
            name="my_flow",
            request=ExecuteFlowRequest(parameters={}),
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_flow_rejects_an_unknown_flow(tmp_path: Path) -> None:
    """Executing an unknown flow is reported as not found."""
    with pytest.raises(HTTPException) as exc_info:
        await _service(tmp_path).execute_flow(
            name="missing",
            request=ExecuteFlowRequest(parameters={}),
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_flow_reports_a_dispatch_failure(tmp_path: Path) -> None:
    """A Prefect dispatch failure is surfaced as a server error."""
    repo = _FakeFlowRepository(flow=_make_flow(Path("/tmp/my_flow.py")))
    service = _service(
        tmp_path,
        repo=repo,
        coordinator=_StubCoordinator(dispatch_failure=FlowDispatchError("prefect is down")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_flow(
            name="my_flow",
            request=ExecuteFlowRequest(parameters={}),
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to execute flow: prefect is down"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("execution_name", "expected_flow_name"),
    [(None, "re-execute:CheckRabi"), ("agent:CheckRabi", "agent:CheckRabi")],
)
async def test_execute_single_task_uses_the_requested_execution_name(
    tmp_path: Path,
    execution_name: str | None,
    expected_flow_name: str,
) -> None:
    """The execution name becomes the flow name of the single-task run."""
    coordinator = _StubCoordinator()
    service = _service(tmp_path, coordinator=coordinator)

    await service.execute_single_task_from_snapshot(
        task_name="CheckRabi",
        qid="Q00",
        chip_id="chip-1",
        source_execution_id="execution-1",
        username="operator",
        project_id="project-1",
        execution_name=execution_name,
    )

    call = coordinator.run_calls[0]
    assert call["name"] == expected_flow_name
    assert call["parameters"]["flow_name"] == expected_flow_name
    assert call["parameters"]["persist_output_parameters"] is True
    assert call.get("workflow", False) is False


@pytest.mark.asyncio
async def test_execute_single_task_supports_quick_run_without_snapshot(
    tmp_path: Path,
) -> None:
    """A quick run forwards the explicit overrides without a source execution."""
    coordinator = _StubCoordinator()
    service = _service(tmp_path, coordinator=coordinator)
    task_run_parameters = {"CheckRabi": {"shots": {"value": 100}}}

    await service.execute_single_task_from_snapshot(
        task_name="CheckRabi",
        qid="Q00",
        chip_id="chip-1",
        source_execution_id=None,
        username="operator",
        project_id="project-1",
        execution_name="quick-run:CheckRabi",
        backend_name="fake",
        task_run_parameters=task_run_parameters,
        persist_output_parameters=False,
        update_params=False,
    )

    parameters = coordinator.run_calls[0]["parameters"]
    assert parameters["source_execution_id"] is None
    assert parameters["backend_name"] == "fake"
    assert parameters["task_run_parameters"] == task_run_parameters
    assert parameters["persist_output_parameters"] is False
    assert parameters["update_params"] is False


@pytest.mark.asyncio
async def test_execute_single_task_reports_an_unavailable_system_deployment(
    tmp_path: Path,
) -> None:
    """A worker that has not registered the deployment yet answers 503."""
    service = _service(tmp_path, coordinator=_StubCoordinator(unavailable=True))

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_single_task_from_snapshot(
            task_name="CheckRabi",
            qid="Q00",
            chip_id="chip-1",
            source_execution_id=None,
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 503
    assert "System deployment not available" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_execute_single_task_reports_a_dispatch_failure(tmp_path: Path) -> None:
    """A failed single-task dispatch is surfaced as a server error."""
    service = _service(
        tmp_path,
        coordinator=_StubCoordinator(dispatch_failure=FlowDispatchError("prefect is down")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_single_task_from_snapshot(
            task_name="CheckRabi",
            qid="Q00",
            chip_id="chip-1",
            source_execution_id="execution-1",
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to execute single task: prefect is down"


@pytest.mark.asyncio
async def test_execute_calibration_pipeline_adds_the_pipeline_tag(tmp_path: Path) -> None:
    """Pipeline runs merge their own tags, request tags and the pipeline marker."""
    coordinator = _StubCoordinator()
    service = _service(tmp_path, coordinator=coordinator)
    spec = {"name": "pipe", "steps": [{"task": "CheckRabi"}], "tags": ["auto"]}

    response = await service.execute_calibration_pipeline(
        spec=spec,
        chip_id="chip-1",
        username="operator",
        project_id="project-1",
        tags=["manual"],
    )

    call = coordinator.run_calls[0]
    assert call["name"] == "pipe"
    assert call["tags"] == ["auto", "manual", "pipeline"]
    assert call["parameters"]["spec"] == spec
    assert call["workflow"] is True
    assert response.message == "Calibration pipeline 'pipe' started"


@pytest.mark.asyncio
async def test_execute_calibration_pipeline_reports_a_dispatch_failure(tmp_path: Path) -> None:
    """A failed pipeline dispatch is surfaced as a server error."""
    service = _service(
        tmp_path,
        coordinator=_StubCoordinator(dispatch_failure=FlowDispatchError("prefect is down")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_calibration_pipeline(
            spec={"name": "pipe", "steps": []},
            chip_id="chip-1",
            username="operator",
            project_id="project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to execute calibration pipeline: prefect is down"


@pytest.mark.asyncio
async def test_execute_agent_candidate_apply_dispatches_in_the_background(
    tmp_path: Path,
) -> None:
    """Applying a candidate commit owns no lock and no execution row."""
    coordinator = _StubCoordinator(flow_run_id="flow-run-7")
    service = _service(tmp_path, coordinator=coordinator)

    response = await service.execute_agent_candidate_apply(
        project_id="project-1",
        session_id="session-1",
        commit_id="commit-1",
        push_to_github=True,
    )

    assert coordinator.run_calls == []
    assert coordinator.background_calls[0]["parameters"] == {
        "project_id": "project-1",
        "session_id": "session-1",
        "commit_id": "commit-1",
        "push_to_github": True,
    }
    assert response.execution_id == "flow-run-7"
    assert response.flow_run_id == "flow-run-7"


@pytest.mark.asyncio
async def test_execute_agent_candidate_apply_reports_a_dispatch_failure(
    tmp_path: Path,
) -> None:
    """A failed background dispatch is surfaced as a server error."""
    service = _service(
        tmp_path,
        coordinator=_StubCoordinator(background_failure=FlowDispatchError("prefect is down")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_agent_candidate_apply(
            project_id="project-1",
            session_id="session-1",
            commit_id="commit-1",
            push_to_github=False,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to dispatch agent candidate apply: prefect is down"


def test_check_execution_availability_delegates_the_conflict_decision(tmp_path: Path) -> None:
    """Availability merges saved defaults and asks the coordinator about the scope."""
    repo = _FakeFlowRepository(
        flow=_make_flow(Path("/tmp/my_flow.py"), default_parameters={"mux_ids": [0]})
    )
    coordinator = _StubCoordinator(available=(False, "busy"))
    service = _service(tmp_path, repo=repo, coordinator=coordinator)

    result = service.check_execution_availability(
        ExecutionAvailabilityRequest(flow_name="my_flow", parameters={"chip_id": "chip-9"}),
        "project-1",
    )

    assert result.available is False
    assert result.reason == "busy"
    assert coordinator.availability_calls == [
        {
            "project_id": "project-1",
            "chip_id": "chip-9",
            "parameters": {"mux_ids": [0], "chip_id": "chip-9"},
            "workflow": True,
        }
    ]


def test_availability_rejects_missing_flow(tmp_path: Path) -> None:
    """Availability for an unknown flow is reported as not found."""
    with pytest.raises(HTTPException) as error:
        _service(tmp_path).check_execution_availability(
            ExecutionAvailabilityRequest(flow_name="missing"),
            "project-1",
        )

    assert error.value.status_code == 404


def test_check_execution_availability_asks_for_a_chip_when_none_resolves(
    tmp_path: Path,
) -> None:
    """Without a chip there is no scope to check, so the request is refused early."""
    repo = _FakeFlowRepository(flow=_make_flow(Path("/tmp/my_flow.py"), chip_id=""))
    coordinator = _StubCoordinator()
    service = _service(tmp_path, repo=repo, coordinator=coordinator)

    result = service.check_execution_availability(
        ExecutionAvailabilityRequest(flow_name="my_flow"),
        "project-1",
    )

    assert result.available is False
    assert result.reason == "Select a chip to check execution availability."
    assert coordinator.availability_calls == []


@pytest.mark.asyncio
async def test_template_accessors_delegate_to_the_catalog() -> None:
    """Templates and helper files are served from the shipped workflow tree."""
    service = FlowService(
        flow_repository=cast("MongoFlowRepository", _FakeFlowRepository()),
    )

    templates = await service.list_templates()
    helpers = await service.list_helper_files()

    assert any(template.id == "full_calibration" for template in templates)
    assert "__init__.py" in helpers
    assert await service.get_helper_file("__init__.py") is not None
    assert (await service.get_template("full_calibration")).code


@pytest.mark.asyncio
async def test_save_flow_restores_old_source_when_update_metadata_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On update, a failed metadata write restores the previous source."""
    monkeypatch.setattr(flow_service_module, "format_with_ruff", lambda _path: None)
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(FLOW_CODE, encoding="utf-8")
    repo = _FakeFlowRepository(flow=_make_flow(file_path))
    repo.update_failure = RuntimeError("mongo is down")
    service = _service(tmp_path, repo=repo)

    new_code = FLOW_CODE + "\n# updated\n"
    with pytest.raises(HTTPException) as exc_info:
        await service.save_flow(
            SaveFlowRequest(name="my_flow", code=new_code, chip_id="chip-1"),
            "operator",
            "project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save flow metadata: mongo is down"
    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == FLOW_CODE


@pytest.mark.asyncio
async def test_save_flow_restores_old_source_when_update_registration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On update, a failed registration restores the previous source."""
    monkeypatch.setattr(flow_service_module, "format_with_ruff", lambda _path: None)
    file_path = tmp_path / "user_flows" / "project-1" / "my_flow.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(FLOW_CODE, encoding="utf-8")
    repo = _FakeFlowRepository(flow=_make_flow(file_path))
    service = _service(
        tmp_path,
        repo=repo,
        deployment=_StubDeploymentClient(
            failure=DeploymentRegistrationError("500: worker is down")
        ),
    )

    new_code = FLOW_CODE + "\n# updated\n"
    with pytest.raises(HTTPException) as exc_info:
        await service.save_flow(
            SaveFlowRequest(name="my_flow", code=new_code, chip_id="chip-1"),
            "operator",
            "project-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to register deployment: 500: worker is down"
    assert file_path.exists()
    assert file_path.read_text(encoding="utf-8") == FLOW_CODE
    assert repo.updated == []


@pytest.mark.asyncio
@pytest.mark.parametrize("system_id", [None, "chip-1"])
async def test_execute_flow_checks_system_boundaries_before_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system_id: str | None,
) -> None:
    """Explicit targets must share a System unless the flow declares its System."""
    from qdash.common.config.system_catalog import SystemSplitRequired

    class Catalog:
        def resolve_single(self, qids: list[str], *, mux_ids: list[int] | None = None) -> str:
            raise SystemSplitRequired("chip-1", {"chip-1": ["1"], "chip-1-quel3": ["9"]})

    monkeypatch.setattr("qdash.api.services.system_split._catalog", lambda chip_id: Catalog())
    coordinator = _StubCoordinator()
    service = _service(
        tmp_path,
        repo=_FakeFlowRepository(flow=_make_flow(Path("/tmp/my_flow.py"))),
        coordinator=coordinator,
    )
    parameters: dict[str, Any] = {"qids": ["1", "9"]}
    if system_id is not None:
        parameters["system_id"] = system_id
        response = await service.execute_flow(
            "my_flow", ExecuteFlowRequest(parameters=parameters), "operator", "project-1"
        )
        assert response.execution_id == "exec-1"
        assert len(coordinator.run_calls) == 1
    else:
        with pytest.raises(HTTPException) as info:
            await service.execute_flow(
                "my_flow", ExecuteFlowRequest(parameters=parameters), "operator", "project-1"
            )
        assert info.value.status_code == 400
        assert info.value.detail["code"] == "system_split_required"
        assert info.value.detail["systems"] == {"chip-1": ["1"], "chip-1-quel3": ["9"]}
        assert coordinator.run_calls == []
