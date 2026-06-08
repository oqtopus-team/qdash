"""Tests for chip router endpoints."""

import pytest

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.qubit import QubitDocument
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


class TestChipRouter:
    """Tests for chip-related API endpoints."""

    def test_list_chips_empty(self, test_client, test_project, auth_headers):
        """Test listing chips when no chips exist."""
        response = test_client.get("/chips", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["chips"] == []
        assert data["total"] == 0

    def test_list_chips_with_data(self, test_client, test_project, auth_headers):
        """Test listing chips when chips exist."""
        # Arrange: Create a chip in the database
        chip = ChipDocument(
            chip_id="test_chip_001",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Create some qubits for the chip
        for i in range(3):
            qubit = QubitDocument(
                project_id="test_project",
                username="test_user",
                chip_id="test_chip_001",
                qid=str(i),
                status="pending",
                data={},
                system_info={},
            )
            qubit.insert()

        # Act
        response = test_client.get("/chips", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["chips"]) == 1
        assert data["chips"][0]["chip_id"] == "test_chip_001"
        assert data["chips"][0]["size"] == 64
        assert data["chips"][0]["activity_status"] == "active"
        assert data["chips"][0]["qubit_count"] == 3

    def test_list_chips_filters_by_project(self, test_client, test_project, auth_headers):
        """Test that listing chips only returns chips for the current project."""
        # Arrange: Create chips for different projects
        chip1 = ChipDocument(
            chip_id="chip_project1",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip1.insert()

        chip2 = ChipDocument(
            chip_id="chip_project2",
            username="test_user",
            project_id="other_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip2.insert()

        # Act
        response = test_client.get("/chips", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["chips"]) == 1
        assert data["chips"][0]["chip_id"] == "chip_project1"

    def test_get_chip_success(self, test_client, test_project, auth_headers):
        """Test fetching a specific chip by ID."""
        # Arrange
        chip = ChipDocument(
            chip_id="test_chip_fetch",
            username="test_user",
            project_id="test_project",
            size=144,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act
        response = test_client.get("/chips/test_chip_fetch", headers=auth_headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "test_chip_fetch"
        assert data["size"] == 144
        assert data["activity_status"] == "active"

    def test_get_chip_not_found(self, test_client, test_project, auth_headers):
        """Test fetching a non-existent chip returns 404."""
        response = test_client.get("/chips/nonexistent_chip", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_chip_wrong_project(self, test_client, test_project, auth_headers):
        """Test that fetching another project's chip returns 404."""
        # Arrange: Create a chip for another project
        chip = ChipDocument(
            chip_id="other_project_chip",
            username="test_user",
            project_id="other_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act: Try to fetch from test_project
        response = test_client.get("/chips/other_project_chip", headers=auth_headers)

        # Assert: Should not find the chip (project isolation)
        assert response.status_code == 404

    def test_update_chip_activity_status(self, test_client, test_project, auth_headers):
        """Test updating a chip's activity status."""
        chip = ChipDocument(
            chip_id="test_chip_status",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        response = test_client.patch(
            "/chips/test_chip_status",
            headers=auth_headers,
            json={"activity_status": "inactive"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "test_chip_status"
        assert data["activity_status"] == "inactive"

    def test_update_chip_topology_creates_missing_target_skeletons(
        self, test_client, test_project, auth_headers
    ):
        """Test topology update backfills empty qubit/coupling target rows."""
        chip = ChipDocument(
            chip_id="test_chip_topology",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        response = test_client.patch(
            "/chips/test_chip_topology",
            headers=auth_headers,
            json={"topology_id": "square-lattice-mux-64"},
        )

        assert response.status_code == 200
        assert (
            QubitDocument.find(
                {"project_id": "test_project", "chip_id": "test_chip_topology"}
            ).count()
            == 64
        )
        assert (
            CouplingDocument.find(
                {"project_id": "test_project", "chip_id": "test_chip_topology"}
            ).count()
            > 0
        )

    def test_create_chip_success(self, test_client, test_project, auth_headers):
        """Test creating a new chip."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "new_chip", "size": 64},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "new_chip"
        assert data["size"] == 64
        assert data["activity_status"] == "active"

    def test_create_chip_invalid_size(self, test_client, test_project, auth_headers):
        """Test creating a chip with invalid size returns 400."""
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "invalid_chip", "size": 100},  # Invalid size
        )

        assert response.status_code == 400

    def test_create_chip_duplicate(self, test_client, test_project, auth_headers):
        """Test creating a duplicate chip returns 400."""
        # Arrange: Create initial chip
        chip = ChipDocument(
            chip_id="existing_chip",
            username="test_user",
            project_id="test_project",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act: Try to create duplicate
        response = test_client.post(
            "/chips",
            headers=auth_headers,
            json={"chip_id": "existing_chip", "size": 64},
        )

        # Assert
        assert response.status_code == 400

    def test_list_chips_requires_authentication(self, test_client, test_project):
        """Test that listing chips without auth returns 401."""
        # Act: Request without Authorization header
        response = test_client.get("/chips")

        # Assert
        assert response.status_code == 401

    def test_list_chips_invalid_token(self, test_client, test_project):
        """Test that listing chips with invalid token returns 401."""
        # Act: Request with invalid token
        headers = {
            "Authorization": "Bearer invalid_token",
            "X-Project-Id": "test_project",
        }
        response = test_client.get("/chips", headers=headers)

        # Assert
        assert response.status_code == 401

    def test_admin_cannot_list_chips_for_project_without_membership(self, test_client, init_db):
        """System admins do not bypass project membership for project data APIs."""
        admin = UserDocument(
            username="admin",
            hashed_password="hashed",
            access_token="admin_token",
            default_project_id=None,
            system_role=SystemRole.ADMIN,
            system_info=SystemInfoModel(),
        )
        admin.insert()

        owner = UserDocument(
            username="owner",
            hashed_password="hashed",
            access_token="owner_token",
            default_project_id="owner_project",
            system_info=SystemInfoModel(),
        )
        owner.insert()

        project = ProjectDocument(
            project_id="owner_project",
            name="Owner Project",
            owner_user_id=owner.user_id,
            owner_username="owner",
            system_info=SystemInfoModel(),
        )
        project.insert()

        ProjectMembershipDocument(
            project_id="owner_project",
            user_id=owner.user_id,
            username="owner",
            role=ProjectRole.OWNER,
            status="active",
            invited_by_user_id=owner.user_id,
            invited_by="owner",
        ).insert()

        ChipDocument(
            chip_id="private_chip",
            username="owner",
            project_id="owner_project",
            size=64,
            system_info=SystemInfoModel(),
        ).insert()

        response = test_client.get(
            "/chips",
            headers={
                "Authorization": "Bearer admin_token",
                "X-Project-Id": "owner_project",
            },
        )

        assert response.status_code == 403
