"""Tests for execution router endpoints."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pymongo.database import Database as PyMongoDatabase
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
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
        owner_username="test_user",
    )
    project.insert()

    membership = ProjectMembershipDocument(
        project_id="test_project",
        username="test_user",
        role=ProjectRole.OWNER,
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
        username="viewer_user",
        role=ProjectRole.VIEWER,
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

    def test_re_execute_requires_owner_role(
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


class TestGetExecution:
    """Tests for GET /executions/{execution_id} endpoint."""

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
