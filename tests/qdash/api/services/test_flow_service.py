from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from qdash.api.schemas.flow import ExecuteFlowRequest
from qdash.api.services import flow_service
from qdash.api.services.flow_service import FlowService
from qdash.common.config.path_resolver import (
    execution_calib_data_dir,
    resolve_workflow_path,
    to_container_user_flow_path,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument


def test_resolve_workflow_path_uses_container_path_when_available(tmp_path: Path) -> None:
    """resolve_workflow_path returns the container path when it exists."""
    container_path = tmp_path / "templates"
    container_path.mkdir()

    assert resolve_workflow_path(container_path, "templates") == container_path


def test_resolve_workflow_path_falls_back_to_repo_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_workflow_path falls back to the repo-local templates directory."""
    repo_root = Path(__file__).resolve().parents[4]
    monkeypatch.chdir(repo_root)

    resolved = resolve_workflow_path(Path("/missing/templates"), "templates")

    assert resolved == repo_root / "src/qdash/workflow/templates"


def test_to_deployment_service_path_maps_host_user_flow_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """to_container_user_flow_path maps a host user-flow path to its container path."""
    host_user_flows = tmp_path / "src/qdash/workflow/user_flows"
    flow_path = host_user_flows / "project-1" / "myflow.py"
    assert to_container_user_flow_path(flow_path, runtime_user_flows_dir=host_user_flows) == Path(
        "/app/qdash/workflow/user_flows/project-1/myflow.py"
    )


def test_to_deployment_service_path_leaves_unrelated_path_unchanged() -> None:
    """_to_deployment_service_path leaves an unrelated path unchanged."""
    file_path = Path("/tmp/myflow.py")

    assert flow_service._to_deployment_service_path(file_path) == file_path


@pytest.mark.asyncio
async def test_list_templates_uses_resolved_templates_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_templates returns templates loaded from the resolved templates metadata file."""
    repo_root = Path(__file__).resolve().parents[4]
    templates_dir = repo_root / "src/qdash/workflow/templates"
    monkeypatch.setattr(flow_service, "TEMPLATES_DIR", templates_dir)
    monkeypatch.setattr(flow_service, "TEMPLATES_METADATA_FILE", templates_dir / "templates.json")

    templates = await FlowService(flow_repository=MagicMock()).list_templates()

    assert any(template.id == "full_calibration" for template in templates)


@pytest.mark.parametrize(
    ("execution_name", "expected_flow_name"),
    [
        (None, "re-execute:CheckRabi"),
        ("agent:CheckRabi", "agent:CheckRabi"),
    ],
)
@pytest.mark.asyncio
async def test_execute_single_task_uses_requested_execution_name(
    monkeypatch: pytest.MonkeyPatch,
    execution_name: str | None,
    expected_flow_name: str,
) -> None:
    """execute_single_task_from_snapshot uses the requested execution name as the flow name."""
    captured_parameters: list[dict[str, object]] = []

    class FakeClient:
        """Fake Prefect client that captures flow run creation parameters."""

        async def read_deployment_by_name(self, _name: str) -> SimpleNamespace:
            """Return a stub deployment regardless of the requested name."""
            return SimpleNamespace(id="deployment-1")

        async def create_flow_run_from_deployment(self, **kwargs: object) -> SimpleNamespace:
            """Record the flow run parameters and return a stub flow run."""
            parameters = kwargs["parameters"]
            assert isinstance(parameters, dict)
            captured_parameters.append(parameters)
            return SimpleNamespace(id="flow-run-1")

    class FakeClientContext:
        """Fake async context manager that yields a FakeClient."""

        async def __aenter__(self) -> FakeClient:
            """Return a new FakeClient instance."""
            return FakeClient()

        async def __aexit__(self, *_args: object) -> None:
            """Do nothing on context exit."""
            return

    monkeypatch.setattr(flow_service, "get_client", FakeClientContext)

    await FlowService(flow_repository=MagicMock()).execute_single_task_from_snapshot(
        task_name="CheckRabi",
        qid="Q00",
        chip_id="chip-1",
        source_execution_id="execution-1",
        username="operator",
        project_id="project-1",
        execution_name=execution_name,
    )

    assert captured_parameters[0]["flow_name"] == expected_flow_name
    assert captured_parameters[0]["persist_output_parameters"] is True


@pytest.mark.asyncio
async def test_execute_single_task_from_snapshot_creates_scheduled_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute_single_task_from_snapshot creates a scheduled execution."""
    captured_calls: list[dict[str, object]] = []

    def _stub(self: FlowService, **kwargs: object) -> str:
        """Record the scheduled-execution kwargs and return a fake execution id."""
        captured_calls.append(kwargs)
        return "exec-1"

    monkeypatch.setattr(FlowService, "_create_scheduled_execution", _stub)

    class FakeClient:
        """Fake Prefect client that returns stub deployment and flow run objects."""

        async def read_deployment_by_name(self, _name: str) -> SimpleNamespace:
            """Return a stub deployment regardless of the requested name."""
            return SimpleNamespace(id="deployment-1")

        async def create_flow_run_from_deployment(self, **kwargs: object) -> SimpleNamespace:
            """Return a stub flow run."""
            return SimpleNamespace(id="flow-run-1")

    class FakeClientContext:
        """Fake async context manager that yields a FakeClient."""

        async def __aenter__(self) -> FakeClient:
            """Return a new FakeClient instance."""
            return FakeClient()

        async def __aexit__(self, *_args: object) -> None:
            """Do nothing on context exit."""
            return

    monkeypatch.setattr(flow_service, "get_client", FakeClientContext)

    response = await FlowService(flow_repository=MagicMock()).execute_single_task_from_snapshot(
        task_name="CheckRabi",
        qid="Q00",
        chip_id="chip-1",
        source_execution_id="execution-1",
        username="operator",
        project_id="project-1",
    )

    assert len(captured_calls) == 1
    kwargs = captured_calls[0]
    assert kwargs["chip_id"] == "chip-1"
    assert kwargs["name"] == "re-execute:CheckRabi"
    assert kwargs["flow_run_id"] == "flow-run-1"
    assert kwargs["project_id"] == "project-1"
    assert kwargs["username"] == "operator"
    assert response.execution_id == "exec-1"
    assert response.flow_run_id == "flow-run-1"
    assert "flow-run-1" in response.flow_run_url
    assert response.qdash_ui_url.endswith("/execution/chip-1/exec-1")


def _make_fake_flow(
    *,
    chip_id: str = "flow-chip",
    default_parameters: dict[str, object] | None = None,
    tags: list[str] | None = None,
) -> SimpleNamespace:
    """Build a fake flow object with the given chip id, default parameters, and tags."""
    return SimpleNamespace(
        deployment_id="deployment-1",
        default_parameters=default_parameters or {},
        chip_id=chip_id,
        tags=tags or [],
    )


class _FakeExecuteFlowClient:
    """Fake Prefect client that returns a flow run with a fixed id."""

    def __init__(self, flow_run_id: str) -> None:
        """Store the flow run id to return from create_flow_run_from_deployment."""
        self._flow_run_id = flow_run_id

    async def create_flow_run_from_deployment(self, **kwargs: object) -> SimpleNamespace:
        """Return a stub flow run with the stored id."""
        return SimpleNamespace(id=self._flow_run_id)


class _FakeExecuteFlowClientContext:
    """Fake async context manager that yields a _FakeExecuteFlowClient."""

    def __init__(self, flow_run_id: str) -> None:
        """Store the flow run id to pass to the fake client."""
        self._flow_run_id = flow_run_id

    async def __aenter__(self) -> _FakeExecuteFlowClient:
        """Return a new _FakeExecuteFlowClient instance."""
        return _FakeExecuteFlowClient(self._flow_run_id)

    async def __aexit__(self, *_args: object) -> None:
        """Do nothing on context exit."""
        return


@pytest.mark.asyncio
async def test_execute_flow_resolves_chip_id_from_request_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute_flow uses the chip_id from request parameters over the flow's default chip_id."""
    captured_calls: list[dict[str, object]] = []

    def _stub(self: FlowService, **kwargs: object) -> str:
        """Record the scheduled-execution kwargs and return a fake execution id."""
        captured_calls.append(kwargs)
        return "exec-1"

    monkeypatch.setattr(FlowService, "_create_scheduled_execution", _stub)
    monkeypatch.setattr(
        flow_service, "get_client", lambda: _FakeExecuteFlowClientContext("flow-run-2")
    )

    flow_repo = MagicMock()
    flow_repo.find_by_project_and_name.return_value = _make_fake_flow(chip_id="fallback-chip")

    response = await FlowService(flow_repository=flow_repo).execute_flow(
        name="my-flow",
        request=ExecuteFlowRequest(parameters={"chip_id": "explicit-chip"}),
        username="operator",
        project_id="project-1",
    )

    assert captured_calls[0]["chip_id"] == "explicit-chip"
    assert captured_calls[0]["flow_run_id"] == "flow-run-2"
    assert response.execution_id == "exec-1"
    assert response.flow_run_id == "flow-run-2"
    assert "flow-run-2" in response.flow_run_url
    assert response.qdash_ui_url.endswith("/execution/explicit-chip/exec-1")


@pytest.mark.asyncio
async def test_execute_flow_falls_back_to_flow_chip_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute_flow falls back to the flow's chip_id when request parameters omit it."""
    captured_calls: list[dict[str, object]] = []

    def _stub(self: FlowService, **kwargs: object) -> str:
        """Record the scheduled-execution kwargs and return a fake execution id."""
        captured_calls.append(kwargs)
        return "exec-1"

    monkeypatch.setattr(FlowService, "_create_scheduled_execution", _stub)
    monkeypatch.setattr(
        flow_service, "get_client", lambda: _FakeExecuteFlowClientContext("flow-run-3")
    )

    flow_repo = MagicMock()
    flow_repo.find_by_project_and_name.return_value = _make_fake_flow(chip_id="fallback-chip")

    response = await FlowService(flow_repository=flow_repo).execute_flow(
        name="my-flow",
        request=ExecuteFlowRequest(parameters={}),
        username="operator",
        project_id="project-1",
    )

    assert captured_calls[0]["chip_id"] == "fallback-chip"
    assert captured_calls[0]["flow_run_id"] == "flow-run-3"
    assert response.execution_id == "exec-1"
    assert response.flow_run_id == "flow-run-3"
    assert "flow-run-3" in response.flow_run_url
    assert response.qdash_ui_url.endswith("/execution/fallback-chip/exec-1")


@pytest.mark.asyncio
async def test_execute_flow_falls_back_to_flow_run_id_when_execution_not_precreated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """execute_flow falls back to the flow-run id when no execution row could be pre-created."""

    def _stub(self: FlowService, **kwargs: object) -> None:
        """Simulate a failed scheduled-execution pre-creation."""

    monkeypatch.setattr(FlowService, "_create_scheduled_execution", _stub)
    monkeypatch.setattr(
        flow_service, "get_client", lambda: _FakeExecuteFlowClientContext("flow-run-4")
    )

    flow_repo = MagicMock()
    flow_repo.find_by_project_and_name.return_value = _make_fake_flow(chip_id="")

    response = await FlowService(flow_repository=flow_repo).execute_flow(
        name="my-flow",
        request=ExecuteFlowRequest(parameters={}),
        username="operator",
        project_id="project-1",
    )

    assert response.execution_id == "flow-run-4"
    assert response.flow_run_id == "flow-run-4"
    assert "flow-run-4" in response.flow_run_url
    assert response.qdash_ui_url.endswith("/execution")


@pytest.mark.asyncio
async def test_re_execute_from_snapshot_returns_qdash_execution_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """re_execute_from_snapshot returns the QDash execution id, flow-run id, and URLs."""
    captured_calls: list[dict[str, object]] = []

    def _stub(self: FlowService, **kwargs: object) -> str:
        """Record the scheduled-execution kwargs and return a fake execution id."""
        captured_calls.append(kwargs)
        return "exec-1"

    monkeypatch.setattr(FlowService, "_create_scheduled_execution", _stub)
    monkeypatch.setattr(
        flow_service, "get_client", lambda: _FakeExecuteFlowClientContext("flow-run-5")
    )

    flow_repo = MagicMock()
    flow_repo.find_by_project_and_name.return_value = _make_fake_flow(chip_id="snapshot-chip")

    response = await FlowService(flow_repository=flow_repo).re_execute_from_snapshot(
        flow_name="my-flow",
        source_execution_id="source-exec-1",
        parameter_overrides={},
        username="operator",
        project_id="project-1",
    )

    assert captured_calls[0]["chip_id"] == "snapshot-chip"
    assert response.execution_id == "exec-1"
    assert response.flow_run_id == "flow-run-5"
    assert "flow-run-5" in response.flow_run_url
    assert response.qdash_ui_url.endswith("/execution/snapshot-chip/exec-1")


def test_create_scheduled_execution_returns_none_when_chip_id_empty() -> None:
    """_create_scheduled_execution returns None when chip_id is empty."""
    service = FlowService(flow_repository=MagicMock())

    result = service._create_scheduled_execution(
        project_id="project-1",
        username="operator",
        chip_id="",
        name="my-flow",
        flow_run_id="flow-run-1",
    )

    assert result is None


def test_create_scheduled_execution_swallows_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_create_scheduled_execution returns None when an internal call raises."""

    def _boom(*_args: object, **_kwargs: object) -> str:
        """Raise a RuntimeError to simulate an internal failure."""
        raise RuntimeError("boom")

    monkeypatch.setattr(flow_service, "generate_execution_id", _boom)

    service = FlowService(flow_repository=MagicMock())

    result = service._create_scheduled_execution(
        project_id="project-1",
        username="operator",
        chip_id="chip-1",
        name="my-flow",
        flow_run_id="flow-run-1",
    )

    assert result is None


def test_create_scheduled_execution_persists_execution_history(init_db: object) -> None:
    """_create_scheduled_execution persists a scheduled execution history document."""
    service = FlowService(flow_repository=MagicMock())

    execution_id = service._create_scheduled_execution(
        project_id="project-1",
        username="operator",
        chip_id="chip-1",
        name="my-flow",
        flow_run_id="flow-run-1",
        tags=["tag-a"],
    )

    assert execution_id is not None

    doc = ExecutionHistoryDocument.find_one(
        {"project_id": "project-1", "execution_id": execution_id}
    ).run()

    assert doc is not None
    assert doc.status == "scheduled"
    assert doc.note["flow_run_id"] == "flow-run-1"
    assert doc.start_at is not None
    assert doc.calib_data_path == str(execution_calib_data_dir("operator", execution_id))
