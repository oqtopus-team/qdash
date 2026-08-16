"""Tests for execution router endpoints."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pymongo.database import Database as PyMongoDatabase

from qdash.common.raw_data import PreFitRawData
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.flow import FlowDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def test_project(init_db: PyMongoDatabase[Any]) -> ProjectDocument:
    """Create a test project with owner membership."""
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="test_user",
        role=ProjectRole.OWNER,
        status="active",
        invited_by_user_id=user.user_id,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture
def viewer_user(init_db: PyMongoDatabase[Any]) -> UserDocument:
    """Create a viewer user (non-owner)."""
    user = UserDocument(
        username="viewer_user",
        hashed_password="hashed",
        access_token="viewer_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="viewer_user",
        role=ProjectRole.VIEWER,
        status="active",
        invited_by="test_user",
    )
    membership.insert()

    return user


@pytest.fixture
def editor_user(init_db: PyMongoDatabase[Any]) -> UserDocument:
    """Create an editor user."""
    user = UserDocument(
        username="editor_user",
        hashed_password="hashed",
        access_token="editor_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        user_id=user.user_id,
        username="editor_user",
        role=ProjectRole.EDITOR,
        status="active",
        invited_by="test_user",
    )
    membership.insert()

    return user


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Owner authentication headers."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    """Viewer authentication headers."""
    return {
        "Authorization": "Bearer viewer_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def editor_headers() -> dict[str, str]:
    """Editor authentication headers."""
    return {
        "Authorization": "Bearer editor_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def sample_execution(test_project: ProjectDocument) -> ExecutionHistoryDocument:
    """Create a sample execution history document."""
    execution = ExecutionHistoryDocument(
        project_id="test_project",
        execution_id="exec-001",
        name="test_flow",
        status="completed",
        chip_id="chip-1",
        username="test_user",
        tags=["test"],
        note={},
        calib_data_path="/tmp/calib",
        message="completed",
        system_info=SystemInfoModel(),
        start_at=datetime.now(tz=timezone.utc),
        end_at=datetime.now(tz=timezone.utc),
        elapsed_time=10.0,
    )
    execution.insert()
    return execution


@pytest.fixture
def sample_flow(test_project: ProjectDocument) -> FlowDocument:
    """Create a sample flow document."""
    flow = FlowDocument(
        project_id="test_project",
        name="test_flow",
        username="test_user",
        chip_id="chip-1",
        description="A test flow",
        flow_function_name="run_test_flow",
        default_parameters={"username": "test_user", "chip_id": "chip-1"},
        file_path="/app/flows/test_user/test_flow.py",
        deployment_id="test-deployment-id",
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        tags=["test"],
    )
    flow.insert()
    return flow


CANCEL_FLOW_RUN_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def test_get_execution_lock_status_includes_latest_execution(
    test_client: TestClient,
    test_project: ProjectDocument,
    auth_headers: dict[str, str],
) -> None:
    execution = ExecutionHistoryDocument(
        project_id=test_project.project_id,
        execution_id="exec-running",
        name="quick-run:CheckChevron",
        status="running",
        chip_id="chip-1",
        username="test_user",
        tags=[],
        note={},
        calib_data_path="/tmp/calib",
        message="running",
        system_info=SystemInfoModel(),
        start_at=datetime.now(tz=timezone.utc),
    )
    execution.insert()
    ExecutionLockDocument.lock(test_project.project_id)

    response = test_client.get("/executions/lock-status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "lock": True,
        "execution_id": "exec-running",
        "chip_id": "chip-1",
        "name": "quick-run:CheckChevron",
        "status": "running",
    }


def test_get_figure_by_path_maps_container_calib_data_path(
    test_client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Serve figures stored under the container calib-data mount from host API mode."""
    local_base = tmp_path / "calib_data"
    figure = local_base / "proj-1" / "figure.png"
    figure.parent.mkdir(parents=True)
    figure.write_bytes(b"png")
    monkeypatch.setenv("CALIB_DATA_PATH", str(local_base))

    response = test_client.get(
        "/executions/figure",
        params={"path": "/app/calib_data/proj-1/figure.png"},
    )

    assert response.status_code == 200
    assert response.content == b"png"


def test_download_artifact_by_path(
    test_client: TestClient,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "raw_data.nc"
    artifact.write_bytes(b"netcdf")

    response = test_client.get("/executions/artifact", params={"path": str(artifact)})

    assert response.status_code == 200
    assert response.content == b"netcdf"
    assert response.headers["content-disposition"] == 'attachment; filename="raw_data.nc"'


def test_download_artifacts_as_archive(
    test_client: TestClient,
    tmp_path: Path,
) -> None:
    figure_dir = tmp_path / "figures"
    raw_dir = tmp_path / "raw"
    figure_dir.mkdir()
    raw_dir.mkdir()
    figure = figure_dir / "artifact.json"
    raw_data = raw_dir / "artifact.json"
    figure.write_text('{"data": []}')
    raw_data.write_text("raw")

    response = test_client.get(
        "/executions/artifacts/archive",
        params=[("paths", str(figure)), ("paths", str(raw_data))],
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="artifacts.zip"'
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.namelist() == ["artifact.json", "artifact_2.json"]
        assert archive.read("artifact.json") == b'{"data": []}'
        assert archive.read("artifact_2.json") == b"raw"


def test_preview_artifact_by_path_returns_complex_table(
    test_client: TestClient,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "raw_data.nc"
    PreFitRawData(
        target="Q00",
        data=np.array([1 + 2j, 3 + 4j]),
        axes={"sweep_range": np.array([10.0, 20.0])},
        source_type="test.SweepData",
    ).save_netcdf(artifact)

    response = test_client.get("/executions/artifact/preview", params={"path": str(artifact)})

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "raw_data.nc"
    assert body["target"] == "Q00"
    assert body["source_type"] == "test.SweepData"
    assert body["shape"] == [2]
    assert body["dtype"] == "complex"
    assert body["columns"] == ["sweep_range", "real", "imag", "abs"]
    assert body["rows"] == [
        {"sweep_range": 10.0, "real": 1.0, "imag": 2.0, "abs": pytest.approx(5**0.5)},
        {"sweep_range": 20.0, "real": 3.0, "imag": 4.0, "abs": 5.0},
    ]
    assert body["total_rows"] == 2
    assert body["truncated"] is False


def test_preview_artifact_by_path_rejects_non_netcdf(
    test_client: TestClient,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "figure.json"
    artifact.write_text("{}")

    response = test_client.get("/executions/artifact/preview", params={"path": str(artifact)})

    assert response.status_code == 400


class TestCancelExecution:
    """Tests for POST /executions/{flow_run_id}/cancel endpoint."""

    def test_cancel_success(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test successful cancellation of a running execution."""
        mock_state = MagicMock()
        mock_state.type.value = "RUNNING"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "test_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)
        mock_client.set_flow_run_state = AsyncMock(return_value=None)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == CANCEL_FLOW_RUN_ID
        assert data["status"] == "cancelling"

    def test_cancel_invalid_uuid_returns_400(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cancelling with non-UUID returns 400."""
        response = test_client.post(
            "/executions/not-a-uuid/cancel",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid flow run ID" in response.json()["detail"]

    def test_cancel_wrong_project_returns_403(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cancelling a flow run from another project returns 403."""
        mock_state = MagicMock()
        mock_state.type.value = "RUNNING"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "other_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 403

    def test_cancel_completed_execution_returns_409(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test cancelling a completed execution returns 409."""
        mock_state = MagicMock()
        mock_state.type.value = "COMPLETED"

        mock_flow_run = MagicMock()
        mock_flow_run.state = mock_state
        mock_flow_run.parameters = {"project_id": "test_project"}

        mock_client = MagicMock()
        mock_client.read_flow_run = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.execution_service.get_client", return_value=async_cm):
            response = test_client.post(
                f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
                headers=auth_headers,
            )

        assert response.status_code == 409
        assert "cannot be cancelled" in response.json()["detail"]

    def test_cancel_requires_authentication(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
    ) -> None:
        """Test cancellation without auth returns 401."""
        response = test_client.post(
            f"/executions/{CANCEL_FLOW_RUN_ID}/cancel",
        )
        assert response.status_code == 401


class TestReExecuteFromSnapshot:
    """Tests for POST /executions/{execution_id}/re-execute endpoint."""

    def test_re_execute_success(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
        sample_execution: ExecutionHistoryDocument,
        sample_flow: FlowDocument,
    ) -> None:
        """Test successful re-execution from snapshot."""
        mock_flow_run = MagicMock()
        mock_flow_run.id = "new-exec-id"

        mock_client = MagicMock()
        mock_client.create_flow_run_from_deployment = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.flow_service.get_client", return_value=async_cm):
            response = test_client.post(
                "/executions/exec-001/re-execute",
                headers=auth_headers,
                json={
                    "flow_name": "test_flow",
                    "parameter_overrides": {},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == "new-exec-id"
        assert "re-execution started" in data["message"]

    def test_re_execute_passes_source_execution_id(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
        sample_execution: ExecutionHistoryDocument,
        sample_flow: FlowDocument,
    ) -> None:
        """Test that source_execution_id is passed to Prefect parameters."""
        mock_flow_run = MagicMock()
        mock_flow_run.id = "new-exec-id"

        mock_client = MagicMock()
        mock_client.create_flow_run_from_deployment = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.flow_service.get_client", return_value=async_cm):
            test_client.post(
                "/executions/exec-001/re-execute",
                headers=auth_headers,
                json={
                    "flow_name": "test_flow",
                    "parameter_overrides": {"custom": "value"},
                },
            )

        call_args = mock_client.create_flow_run_from_deployment.call_args
        parameters: dict[str, Any] = call_args.kwargs.get("parameters", {})
        assert parameters["source_execution_id"] == "exec-001"
        assert parameters["project_id"] == "test_project"

    def test_re_execute_source_not_found(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test re-execution with non-existent source execution returns 404."""
        response = test_client.post(
            "/executions/nonexistent/re-execute",
            headers=auth_headers,
            json={
                "flow_name": "test_flow",
                "parameter_overrides": {},
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_re_execute_flow_not_found(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
        sample_execution: ExecutionHistoryDocument,
    ) -> None:
        """Test re-execution when the flow doesn't exist returns 404."""
        response = test_client.post(
            "/executions/exec-001/re-execute",
            headers=auth_headers,
            json={
                "flow_name": "nonexistent_flow",
                "parameter_overrides": {},
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_re_execute_requires_authentication(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        sample_execution: ExecutionHistoryDocument,
    ) -> None:
        """Test re-execution without auth returns 401."""
        response = test_client.post(
            "/executions/exec-001/re-execute",
            json={
                "flow_name": "test_flow",
                "parameter_overrides": {},
            },
        )
        assert response.status_code == 401

    def test_re_execute_rejects_viewer_role(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        viewer_user: UserDocument,
        viewer_headers: dict[str, str],
        sample_execution: ExecutionHistoryDocument,
    ) -> None:
        """Test re-execution with viewer role returns 403."""
        response = test_client.post(
            "/executions/exec-001/re-execute",
            headers=viewer_headers,
            json={
                "flow_name": "test_flow",
                "parameter_overrides": {},
            },
        )
        assert response.status_code == 403

    @patch("qdash.api.services.flow_service.FlowService.re_execute_from_snapshot")
    def test_re_execute_allows_editor_for_own_execution(
        self,
        mock_re_execute: AsyncMock,
        test_client: TestClient,
        test_project: ProjectDocument,
        editor_user: UserDocument,
        editor_headers: dict[str, str],
    ) -> None:
        """Test editors can re-execute their own executions."""
        execution = ExecutionHistoryDocument(
            project_id="test_project",
            execution_id="exec-editor",
            name="test_flow",
            status="completed",
            chip_id="chip-1",
            username="editor_user",
            tags=["test"],
            note={},
            calib_data_path="/tmp/calib",
            message="completed",
            system_info=SystemInfoModel(),
            start_at=datetime.now(tz=timezone.utc),
            end_at=datetime.now(tz=timezone.utc),
            elapsed_time=10.0,
        )
        execution.insert()
        mock_re_execute.return_value = {
            "execution_id": "exec-new",
            "flow_run_url": "http://prefect.local/runs/run-123",
            "qdash_ui_url": "http://qdash.local/executions/exec-new",
            "message": "Flow re-execution started",
        }

        response = test_client.post(
            "/executions/exec-editor/re-execute",
            headers=editor_headers,
            json={
                "flow_name": "test_flow",
                "parameter_overrides": {},
            },
        )

        assert response.status_code == 200


class TestListExecutions:
    """Tests for GET /executions endpoint."""

    def test_list_executions_empty(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test listing executions when none exist."""
        response = test_client.get(
            "/executions",
            headers=auth_headers,
            params={"chip_id": "chip-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["executions"] == []
        assert data["total"] == 0

    def test_list_executions_with_data(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
        sample_execution: ExecutionHistoryDocument,
    ) -> None:
        """Test listing executions returns data."""
        response = test_client.get(
            "/executions",
            headers=auth_headers,
            params={"chip_id": "chip-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) == 1
        assert data["executions"][0]["execution_id"] == "exec-001"
        assert data["total"] == 1

    def test_list_executions_total_reflects_all_records(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that total reflects all records even when pagination limits results."""
        now = datetime.now(tz=timezone.utc)
        for i in range(3):
            execution = ExecutionHistoryDocument(
                project_id="test_project",
                execution_id=f"exec-multi-{i:03d}",
                name="test_flow",
                status="completed",
                chip_id="chip-1",
                username="test_user",
                tags=["test"],
                note={},
                calib_data_path="/tmp/calib",
                message="completed",
                system_info=SystemInfoModel(),
                start_at=datetime(2024, 1, i + 1, tzinfo=timezone.utc),
                end_at=now,
                elapsed_time=10.0,
            )
            execution.insert()

        response = test_client.get(
            "/executions",
            headers=auth_headers,
            params={"chip_id": "chip-1", "skip": 2, "limit": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["executions"]) == 1
        assert data["total"] == 3


class TestGetExecution:
    """Tests for GET /executions/{execution_id} endpoint."""

    def test_get_execution_by_prefect_flow_run_id(
        self,
        test_client: TestClient,
        sample_execution: ExecutionHistoryDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Resolve a dispatched Prefect flow run to its QDash execution."""
        sample_execution.note = {"flow_run_id": "flow-run-001"}
        sample_execution.save()

        response = test_client.get(
            "/executions/flow-run-001",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "test_flow-exec-001"

    def test_get_execution_not_found(
        self,
        test_client: TestClient,
        test_project: ProjectDocument,
        auth_headers: dict[str, str],
    ) -> None:
        """Test getting non-existent execution returns 404."""
        response = test_client.get(
            "/executions/nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 404
