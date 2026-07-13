from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from qdash.api.services import flow_service
from qdash.api.services.flow_service import FlowService
from qdash.common.config.path_resolver import resolve_workflow_path, to_container_user_flow_path


def test_resolve_workflow_path_uses_container_path_when_available(tmp_path: Path) -> None:
    container_path = tmp_path / "templates"
    container_path.mkdir()

    assert resolve_workflow_path(container_path, "templates") == container_path


def test_resolve_workflow_path_falls_back_to_repo_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    monkeypatch.chdir(repo_root)

    resolved = resolve_workflow_path(Path("/missing/templates"), "templates")

    assert resolved == repo_root / "src/qdash/workflow/templates"


def test_to_deployment_service_path_maps_host_user_flow_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    host_user_flows = tmp_path / "src/qdash/workflow/user_flows"
    flow_path = host_user_flows / "project-1" / "myflow.py"
    assert to_container_user_flow_path(flow_path, runtime_user_flows_dir=host_user_flows) == Path(
        "/app/qdash/workflow/user_flows/project-1/myflow.py"
    )


def test_to_deployment_service_path_leaves_unrelated_path_unchanged() -> None:
    file_path = Path("/tmp/myflow.py")

    assert flow_service._to_deployment_service_path(file_path) == file_path


@pytest.mark.asyncio
async def test_list_templates_uses_resolved_templates_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    captured_parameters: list[dict[str, object]] = []

    class FakeClient:
        async def read_deployment_by_name(self, _name: str) -> SimpleNamespace:
            return SimpleNamespace(id="deployment-1")

        async def create_flow_run_from_deployment(self, **kwargs: object) -> SimpleNamespace:
            parameters = kwargs["parameters"]
            assert isinstance(parameters, dict)
            captured_parameters.append(parameters)
            return SimpleNamespace(id="flow-run-1")

    class FakeClientContext:
        async def __aenter__(self) -> FakeClient:
            return FakeClient()

        async def __aexit__(self, *_args: object) -> None:
            return None

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
