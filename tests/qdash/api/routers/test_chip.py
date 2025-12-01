"""Tests for chip router endpoints."""

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument


class TestChipRouter:
    """Tests for chip-related API endpoints."""

    def test_list_chips_empty(self, test_client):
        """Test listing chips when no chips exist."""
        response = test_client.get(
            "/api/chip",
            headers={"X-Username": "test_user"},
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_chips_with_data(self, test_client):
        """Test listing chips when chips exist."""
        # Arrange: Create a chip in the database
        chip = ChipDocument(
            chip_id="test_chip_001",
            username="test_user",
            size=64,
            qubits={},
            couplings={},
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act
        response = test_client.get(
            "/api/chip",
            headers={"X-Username": "test_user"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["chip_id"] == "test_chip_001"
        assert data[0]["size"] == 64

    def test_list_chips_filters_by_user(self, test_client):
        """Test that listing chips only returns chips for the authenticated user."""
        # Arrange: Create chips for different users
        chip1 = ChipDocument(
            chip_id="chip_user1",
            username="user1",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip1.insert()

        chip2 = ChipDocument(
            chip_id="chip_user2",
            username="user2",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip2.insert()

        # Act
        response = test_client.get(
            "/api/chip",
            headers={"X-Username": "user1"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["chip_id"] == "chip_user1"

    def test_fetch_chip_success(self, test_client):
        """Test fetching a specific chip by ID."""
        # Arrange
        chip = ChipDocument(
            chip_id="test_chip_fetch",
            username="test_user",
            size=144,
            qubits={},
            couplings={},
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act
        response = test_client.get(
            "/api/chip/test_chip_fetch",
            headers={"X-Username": "test_user"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "test_chip_fetch"
        assert data["size"] == 144

    def test_fetch_chip_not_found(self, test_client):
        """Test fetching a non-existent chip returns 404."""
        response = test_client.get(
            "/api/chip/nonexistent_chip",
            headers={"X-Username": "test_user"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_fetch_chip_wrong_user(self, test_client):
        """Test that fetching another user's chip returns 404."""
        # Arrange: Create a chip for user1
        chip = ChipDocument(
            chip_id="user1_chip",
            username="user1",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act: Try to fetch as user2
        response = test_client.get(
            "/api/chip/user1_chip",
            headers={"X-Username": "user2"},
        )

        # Assert: Should not find the chip (access control)
        assert response.status_code == 404

    def test_create_chip_success(self, test_client):
        """Test creating a new chip."""
        response = test_client.post(
            "/api/chip",
            headers={"X-Username": "test_user"},
            json={"chip_id": "new_chip", "size": 64},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chip_id"] == "new_chip"
        assert data["size"] == 64

    def test_create_chip_invalid_size(self, test_client):
        """Test creating a chip with invalid size returns 400."""
        response = test_client.post(
            "/api/chip",
            headers={"X-Username": "test_user"},
            json={"chip_id": "invalid_chip", "size": 100},  # Invalid size
        )

        assert response.status_code == 400

    def test_create_chip_duplicate(self, test_client):
        """Test creating a duplicate chip returns 400."""
        # Arrange: Create initial chip
        chip = ChipDocument(
            chip_id="existing_chip",
            username="test_user",
            size=64,
            system_info=SystemInfoModel(),
        )
        chip.insert()

        # Act: Try to create duplicate
        response = test_client.post(
            "/api/chip",
            headers={"X-Username": "test_user"},
            json={"chip_id": "existing_chip", "size": 64},
        )

        # Assert
        assert response.status_code == 400
