"""Tests for backend router endpoints."""

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.backend import BackendDocument
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


class TestBackendRouter:
    """Tests for backend-related API endpoints."""

    def test_list_backends_empty(self, test_client, test_project, auth_headers):
        """Test listing backends when no backends exist."""
        response = test_client.get("/backends", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["backends"] == []

    def test_list_backends_with_data(self, test_client, test_project, auth_headers):
        """Test listing backends when backends exist."""
        # Arrange: Create a backend in the database
        backend = BackendDocument(
            name="qubex",
            username="test_user",
            project_id="test_project",
            system_info=SystemInfoModel(),
        )
        backend.insert()

        # Act
        response = test_client.get("/backends", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["backends"]) == 1
        assert data["backends"][0]["name"] == "qubex"

    def test_list_backends_filters_by_project(self, test_client, test_project, auth_headers):
        """Test that listing backends only returns backends for the current project."""
        # Arrange: Create backends for different projects
        backend1 = BackendDocument(
            name="backend_project1",
            username="test_user",
            project_id="test_project",
            system_info=SystemInfoModel(),
        )
        backend1.insert()

        backend2 = BackendDocument(
            name="backend_project2",
            username="test_user",
            project_id="other_project",
            system_info=SystemInfoModel(),
        )
        backend2.insert()

        # Act
        response = test_client.get("/backends", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["backends"]) == 1
        assert data["backends"][0]["name"] == "backend_project1"

    def test_list_backends_requires_authentication(self, test_client, test_project):
        """Test that listing backends without auth returns 401."""
        # Act: Request without Authorization header
        response = test_client.get("/backends")

        # Assert
        assert response.status_code == 401

    def test_list_backends_invalid_token(self, test_client, test_project):
        """Test that listing backends with invalid token returns 401."""
        # Act: Request with invalid token
        headers = {
            "Authorization": "Bearer invalid_token",
            "X-Project-Id": "test_project",
        }
        response = test_client.get("/backends", headers=headers)

        # Assert
        assert response.status_code == 401
