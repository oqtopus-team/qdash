"""Tests for flow router endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.flow import FlowDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


@pytest.fixture
def test_project(init_db):
    """Create a test project with owner membership."""
    # Create user
    user = UserDocument(
        username="test_user",
        hashed_password="hashed",
        access_token="test_token",
        default_project_id="test_project",
        system_info=SystemInfoModel(),
    )
    user.insert()

    # Create project
    project = ProjectDocument(
        project_id="test_project",
        name="Test Project",
        owner_username="test_user",
    )
    project.insert()

    # Create membership
    membership = ProjectMembershipDocument(
        project_id="test_project",
        username="test_user",
        role=ProjectRole.OWNER,
        invited_by="test_user",
    )
    membership.insert()

    return project


@pytest.fixture
def auth_headers():
    """Get authentication headers with project context."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def sample_flow(test_project):
    """Create a sample flow in the database."""
    flow = FlowDocument(
        project_id="test_project",
        name="test_flow",
        username="test_user",
        chip_id="test_chip",
        description="A test flow",
        flow_function_name="run_test_flow",
        default_parameters={"username": "test_user", "chip_id": "test_chip", "qids": ["0", "1"]},
        file_path="/app/flows/test_user/test_flow.py",
        deployment_id="test-deployment-id",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        tags=["test"],
    )
    flow.insert()
    return flow


class TestFlowRouter:
    """Tests for flow-related API endpoints."""

    def test_list_flows_empty(self, test_client, test_project, auth_headers):
        """Test listing flows when no flows exist."""
        response = test_client.get("/flows", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["flows"] == []

    def test_list_flows_with_data(self, test_client, test_project, auth_headers, sample_flow):
        """Test listing flows when flows exist."""
        response = test_client.get("/flows", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["name"] == "test_flow"

    def test_list_flows_filters_by_project(self, test_client, test_project, auth_headers):
        """Test that listing flows only returns flows for the current project."""
        # Arrange: Create flows for different projects
        flow1 = FlowDocument(
            project_id="test_project",
            name="flow_project1",
            username="test_user",
            chip_id="chip1",
            flow_function_name="run_flow1",
            file_path="/app/flows/test_user/flow1.py",
        )
        flow1.insert()

        flow2 = FlowDocument(
            project_id="other_project",
            name="flow_project2",
            username="test_user",
            chip_id="chip2",
            flow_function_name="run_flow2",
            file_path="/app/flows/test_user/flow2.py",
        )
        flow2.insert()

        # Act
        response = test_client.get("/flows", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["name"] == "flow_project1"

    def test_list_flows_requires_authentication(self, test_client, test_project):
        """Test that listing flows without auth returns 401."""
        response = test_client.get("/flows")
        assert response.status_code == 401

    def test_list_flows_invalid_token(self, test_client, test_project):
        """Test that listing flows with invalid token returns 401."""
        headers = {
            "Authorization": "Bearer invalid_token",
            "X-Project-Id": "test_project",
        }
        response = test_client.get("/flows", headers=headers)
        assert response.status_code == 401


class TestFlowExecution:
    """Tests for flow execution endpoint."""

    def test_execute_flow_passes_project_id_and_flow_name(
        self, test_client, test_project, auth_headers, sample_flow
    ):
        """Test that execute_flow passes project_id and flow_name to Prefect parameters.

        project_id is passed for multi-tenancy support, allowing workflows to
        operate within the correct project context.
        """
        # Arrange: Mock Prefect client
        mock_flow_run = MagicMock()
        mock_flow_run.id = "test-flow-run-id"

        mock_client = MagicMock()
        mock_client.create_flow_run_from_deployment = AsyncMock(return_value=mock_flow_run)

        # Create async context manager mock
        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("prefect.get_client", return_value=async_cm):
            # Act
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {}},
            )

        # Assert
        assert response.status_code == 200

        # Verify parameters passed to Prefect
        call_args = mock_client.create_flow_run_from_deployment.call_args
        parameters = call_args.kwargs.get("parameters", {})

        # project_id should be passed for multi-tenancy
        assert "project_id" in parameters
        assert parameters["project_id"] == "test_project"

        # flow_name should be passed for display purposes
        assert "flow_name" in parameters
        assert parameters["flow_name"] == "test_flow"

    def test_execute_flow_merges_default_parameters(
        self, test_client, test_project, auth_headers, sample_flow
    ):
        """Test that execute_flow merges request parameters with default_parameters."""
        # Arrange
        mock_flow_run = MagicMock()
        mock_flow_run.id = "test-flow-run-id"

        mock_client = MagicMock()
        mock_client.create_flow_run_from_deployment = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("prefect.get_client", return_value=async_cm):
            # Act: Execute with custom parameters
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=auth_headers,
                json={"parameters": {"custom_param": "custom_value"}},
            )

        # Assert
        assert response.status_code == 200

        call_args = mock_client.create_flow_run_from_deployment.call_args
        parameters = call_args.kwargs.get("parameters", {})

        # Default parameters should be present
        assert parameters.get("username") == "test_user"
        assert parameters.get("chip_id") == "test_chip"
        assert parameters.get("qids") == ["0", "1"]

        # Custom parameter should be merged
        assert parameters.get("custom_param") == "custom_value"

        # flow_name should be added
        assert parameters.get("flow_name") == "test_flow"

    def test_execute_flow_not_found(self, test_client, test_project, auth_headers):
        """Test that executing non-existent flow returns 404."""
        response = test_client.post(
            "/flows/nonexistent_flow/execute",
            headers=auth_headers,
            json={"parameters": {}},
        )
        assert response.status_code == 404

    def test_execute_flow_requires_authentication(self, test_client, test_project, sample_flow):
        """Test that executing flow without auth returns 401."""
        response = test_client.post(
            "/flows/test_flow/execute",
            json={"parameters": {}},
        )
        assert response.status_code == 401

    def test_execute_flow_wrong_project(self, test_client, test_project, auth_headers):
        """Test that executing another project's flow returns 404."""
        # Arrange: Create a flow for another project
        flow = FlowDocument(
            project_id="other_project",
            name="other_flow",
            username="test_user",
            chip_id="chip",
            flow_function_name="run_flow",
            file_path="/app/flows/test_user/other_flow.py",
            deployment_id="other-deployment-id",
        )
        flow.insert()

        # Act: Try to execute from test_project
        response = test_client.post(
            "/flows/other_flow/execute",
            headers=auth_headers,
            json={"parameters": {}},
        )

        # Assert: Should not find the flow (project isolation)
        assert response.status_code == 404
