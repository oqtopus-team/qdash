"""qdash.sdk's QDash.workflows against the real /flows routes.

The SDK's QDashClient sends its requests through FastAPI's TestClient, so list, get and run
reach the flow service and its project scoping. Prefect dispatch is patched; nothing runs.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from qdash.client import QDashClient, QDashConfig
from qdash.dbmodel.flow import FlowDocument
from qdash.sdk import QDash, QDashNotFoundError
from tests.qdash.api.routers.test_flow import test_project  # noqa: F401 - pytest fixture

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

SOURCE = "def coherence_check(qids=None, shots=1024):\n    pass\n"


def save(project_id: str, name: str, file_path: Path) -> None:
    FlowDocument(
        project_id=project_id,
        name=name,
        username="test_user",
        chip_id="64Qv3",
        description="T1 and T2 echo",
        flow_function_name=name,
        default_parameters={"qids": ["0"], "shots": 1024},
        file_path=str(file_path),
        deployment_id=f"{name}-deployment",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        tags=["coherence"],
    ).insert()


@pytest.fixture
def flows(test_project: Any, tmp_path: Path) -> None:  # noqa: F811
    path = tmp_path / "coherence_check.py"
    path.write_text(SOURCE, encoding="utf-8")
    save("test_project", "coherence_check", path)
    save("other_project", "other_check", path)


@pytest.fixture
def qdash(test_client: Any, flows: None) -> Iterator[QDash]:
    config = QDashConfig(
        base_url=str(test_client.base_url), api_token="test_token", project_id="test_project"
    )
    with QDash(QDashClient(config, http_client=test_client)) as session:
        yield session


def run_parameters(qdash: QDash, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    create_flow_run = AsyncMock(return_value="flow-run-1")
    with patch(
        "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
        new=create_flow_run,
    ):
        run = qdash.workflows.get("coherence_check").run(**kwargs)
    create_flow_run.assert_awaited_once()
    return run, create_flow_run.call_args.kwargs["parameters"]


def test_list_and_get_read_the_project_workflows_without_dispatch(qdash: QDash) -> None:
    create_flow_run = AsyncMock()
    with patch(
        "qdash.api.services.flow_service.prefect_gateway.PrefectGateway.create_flow_run",
        new=create_flow_run,
    ):
        names = [(w.name, w.chip_id) for w in qdash.workflows.list()]
        workflow = qdash.workflows.get("coherence_check")

    assert names == [("coherence_check", "64Qv3")]
    assert (workflow.name, workflow.chip_id) == ("coherence_check", "64Qv3")
    assert workflow.default_parameters == {"qids": ["0"], "shots": 1024}
    assert workflow.detail.code == SOURCE
    create_flow_run.assert_not_awaited()


def test_run_overrides_the_saved_parameters_for_the_run(qdash: QDash) -> None:
    run, parameters = run_parameters(qdash, parameters={"qids": ["0", "1"]})

    assert run.response.flow_run_id == "flow-run-1"
    assert run.execution_id
    assert parameters["qids"] == ["0", "1"]
    assert parameters["shots"] == 1024
    assert parameters["project_id"] == "test_project"
    assert parameters["flow_name"] == "coherence_check"


def test_run_without_parameters_runs_the_saved_defaults(qdash: QDash) -> None:
    _, parameters = run_parameters(qdash)

    assert parameters["qids"] == ["0"]
    assert parameters["shots"] == 1024


def test_another_projects_workflow_is_not_found(qdash: QDash) -> None:
    with pytest.raises(QDashNotFoundError):
        qdash.workflows.get("other_check")
    with pytest.raises(QDashNotFoundError):
        qdash.workflows.run("other_check")
