"""Tests for flow router endpoints."""

from datetime import datetime
from pathlib import Path
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
        owner_user_id=user.user_id,
        owner_username="test_user",
    )
    project.insert()

    # Create membership
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
def auth_headers():
    """Get authentication headers with project context."""
    return {
        "Authorization": "Bearer test_token",
        "X-Project-Id": "test_project",
    }


@pytest.fixture
def editor_auth_headers(test_project):
    """Create an editor user and return authentication headers."""
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

    return {
        "Authorization": "Bearer editor_token",
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
        assert data["flows"][0]["created_by"] == "test_user"
        assert data["flows"][0]["file_exists"] is False

    def test_list_flows_marks_existing_files(
        self, test_client, test_project, auth_headers, tmp_path
    ):
        """Test listing flows reports whether the source file still exists."""
        flow_path = tmp_path / "existing_flow.py"
        flow_path.write_text("from prefect import flow\n", encoding="utf-8")
        flow = FlowDocument(
            project_id="test_project",
            name="existing_flow",
            username="test_user",
            chip_id="test_chip",
            description="An existing flow",
            flow_function_name="run_existing_flow",
            file_path=str(flow_path),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
        )
        flow.insert()

        response = test_client.get("/flows", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["flows"][0]["name"] == "existing_flow"
        assert data["flows"][0]["file_exists"] is True

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

    def test_list_flows_includes_other_project_members_flows(
        self, test_client, test_project, editor_auth_headers, sample_flow
    ):
        """Test that project members can see flows created by other members."""
        response = test_client.get("/flows", headers=editor_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["flows"]) == 1
        assert data["flows"][0]["name"] == "test_flow"

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

        with patch("qdash.api.services.flow_service.get_client", return_value=async_cm):
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

        with patch("qdash.api.services.flow_service.get_client", return_value=async_cm):
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

    def test_execute_flow_created_by_other_member_uses_requesting_user(
        self, test_client, test_project, editor_auth_headers, sample_flow
    ):
        """Test that project members can execute shared flows as themselves."""
        mock_flow_run = MagicMock()
        mock_flow_run.id = "test-flow-run-id"

        mock_client = MagicMock()
        mock_client.create_flow_run_from_deployment = AsyncMock(return_value=mock_flow_run)

        async_cm = MagicMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_client)
        async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("qdash.api.services.flow_service.get_client", return_value=async_cm):
            response = test_client.post(
                "/flows/test_flow/execute",
                headers=editor_auth_headers,
                json={"parameters": {}},
            )

        assert response.status_code == 200

        call_args = mock_client.create_flow_run_from_deployment.call_args
        parameters = call_args.kwargs.get("parameters", {})
        assert parameters["username"] == "editor_user"
        assert parameters["project_id"] == "test_project"


class TestFlowTemplates:
    """Tests for flow template endpoints."""

    def test_get_full_calibration_template_includes_configure_all(
        self, test_client, test_project, auth_headers
    ):
        """Test that the full calibration template starts with ConfigureAll."""
        repo_root = Path(__file__).resolve().parents[4]
        templates_dir = repo_root / "src/qdash/workflow/templates"

        with (
            patch("qdash.api.services.flow_service.TEMPLATES_DIR", templates_dir),
            patch(
                "qdash.api.services.flow_service.TEMPLATES_METADATA_FILE",
                templates_dir / "templates.json",
            ),
        ):
            response = test_client.get("/flows/templates/full_calibration", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "full_calibration"
        assert "ConfigureAll -> 1Q Check" in data["description"]
        assert "ConfigureAll()," in data["code"]

    def test_get_fast_full_calibration_template_includes_shortened_tasks(
        self, test_client, test_project, auth_headers
    ):
        """Test that the fast full calibration template is registered and loadable."""
        repo_root = Path(__file__).resolve().parents[4]
        templates_dir = repo_root / "src/qdash/workflow/templates"

        with (
            patch("qdash.api.services.flow_service.TEMPLATES_DIR", templates_dir),
            patch(
                "qdash.api.services.flow_service.TEMPLATES_METADATA_FILE",
                templates_dir / "templates.json",
            ),
        ):
            response = test_client.get(
                "/flows/templates/fast_full_calibration", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "fast_full_calibration"
        assert "Shortened full calibration" in data["description"]
        fine_tune_tasks_block = data["code"].split("FAST_1Q_FINE_TUNE_TASKS", 1)[1].split("]", 1)[0]
        assert "CheckT1Average" not in fine_tune_tasks_block
