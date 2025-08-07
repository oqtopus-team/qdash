"""Test for chip dbmodel with Bunnet and MongoDB testcontainers."""

from collections.abc import Generator
from typing import cast

import pytest
from bunnet import init_bunnet
from pymongo import MongoClient
from qdash.datamodel.coupling import CouplingModel, EdgeInfoModel
from qdash.datamodel.qubit import NodeInfoModel, PositionModel, QubitModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument
from testcontainers.mongodb import MongoDbContainer

# Test constants
TEST_DATE = "2024-01-01T00:00:00Z"
TEST_USERNAME = "test_user"
DEFAULT_POSITION_X = 0.0
DEFAULT_POSITION_Y = 0.0
DEFAULT_COUPLING_SIZE = 1
DEFAULT_COUPLING_FILL = "#000000"


@pytest.fixture(scope="module")
def mongodb_container() -> Generator[MongoDbContainer, None, None]:
    """Create MongoDB test container."""
    container = MongoDbContainer("mongo:7.0")
    container.start()
    yield container
    container.stop()


@pytest.fixture()
def mongodb_client(mongodb_container: MongoDbContainer) -> Generator[MongoClient, None, None]:
    """Create MongoDB client for test."""
    connection_string = mongodb_container.get_connection_url()
    client: MongoClient = MongoClient(connection_string)
    yield client
    client.close()


@pytest.fixture()
def system_info() -> SystemInfoModel:
    """Create test system info."""
    return SystemInfoModel(
        created_at=TEST_DATE,
        updated_at=TEST_DATE,
    )


@pytest.fixture(autouse=True)
def _init_db(mongodb_client: MongoClient) -> None:
    init_bunnet(
        database=mongodb_client.test_db,
        document_models=[ChipDocument],
    )
    # Clear collection before each test
    ChipDocument.get_motor_collection().drop()


def create_test_qubit(qid: str, x_180_length: float = 30.0) -> QubitModel:
    """Helper function to create a test qubit."""
    node_info = NodeInfoModel(position=PositionModel(x=DEFAULT_POSITION_X, y=DEFAULT_POSITION_Y))
    return QubitModel(
        username=TEST_USERNAME,
        chip_id="test_chip",
        status="active",
        qid=qid,
        data={"x_180_length": x_180_length},
        node_info=node_info,
    )


def create_test_coupling(qid: str, source: str, target: str) -> CouplingModel:
    """Helper function to create a test coupling."""
    edge_info = EdgeInfoModel(
        source=source,
        target=target,
        size=DEFAULT_COUPLING_SIZE,
        fill=DEFAULT_COUPLING_FILL,
    )
    return CouplingModel(
        username=TEST_USERNAME,
        chip_id="test_chip",
        status="active",
        qid=qid,
        data={},
        edge_info=edge_info,
    )


def test_create_chip_document(system_info: SystemInfoModel) -> None:
    """Test creating a chip document."""
    # Arrange
    chip_id = "test_chip_001"
    expected_size = 4
    expected_q0_length = 30.0
    expected_q1_length = 32.0

    chip = ChipDocument(
        chip_id=chip_id,
        username=TEST_USERNAME,
        size=expected_size,
        qubits={
            "Q0": create_test_qubit("Q0", expected_q0_length),
            "Q1": create_test_qubit("Q1", expected_q1_length),
        },
        couplings={
            "Q0-Q1": create_test_coupling("Q0-Q1", "Q0", "Q1"),
        },
        system_info=system_info,
    )

    # Act
    chip.insert()
    retrieved_chip = ChipDocument.find_one(ChipDocument.chip_id == chip_id).run()

    # Assert
    assert retrieved_chip is not None, f"Chip with id '{chip_id}' should exist"
    assert retrieved_chip.chip_id == chip_id, "Chip ID should match"
    assert retrieved_chip.username == TEST_USERNAME, "Username should match"
    assert retrieved_chip.size == expected_size, f"Size should be {expected_size}"
    assert len(retrieved_chip.qubits) == 2, "Should have 2 qubits"
    assert "Q0" in retrieved_chip.qubits, "Q0 should exist in qubits"
    assert "Q1" in retrieved_chip.qubits, "Q1 should exist in qubits"
    assert (
        retrieved_chip.qubits["Q0"].data["x_180_length"] == expected_q0_length
    ), "Q0 x_180_length should match"
    assert (
        retrieved_chip.qubits["Q1"].data["x_180_length"] == expected_q1_length
    ), "Q1 x_180_length should match"
    assert len(retrieved_chip.couplings) == 1, "Should have 1 coupling"
    assert "Q0-Q1" in retrieved_chip.couplings, "Q0-Q1 coupling should exist"


def test_update_qubit(system_info: SystemInfoModel) -> None:
    """Test updating a qubit in chip document."""
    # Arrange
    chip_id = "test_chip_002"
    initial_q0_length = 30.0
    initial_q1_length = 32.0
    updated_q0_length = 35.0

    chip = ChipDocument(
        chip_id=chip_id,
        username=TEST_USERNAME,
        size=2,
        qubits={
            "Q0": create_test_qubit("Q0", initial_q0_length),
            "Q1": create_test_qubit("Q1", initial_q1_length),
        },
        system_info=system_info,
    )
    chip.insert()

    # Act
    updated_qubit = create_test_qubit("Q0", updated_q0_length)
    chip.update_qubit("Q0", updated_qubit)
    chip.save()

    # Assert
    retrieved_chip = ChipDocument.find_one(ChipDocument.chip_id == chip_id).run()
    assert retrieved_chip is not None, f"Chip with id '{chip_id}' should exist"
    assert (
        retrieved_chip.qubits["Q0"].data["x_180_length"] == updated_q0_length
    ), "Q0 should be updated"
    assert (
        retrieved_chip.qubits["Q1"].data["x_180_length"] == initial_q1_length
    ), "Q1 should remain unchanged"


def test_update_nonexistent_qubit(system_info: SystemInfoModel) -> None:
    """Test updating a non-existent qubit raises ValueError."""
    # Arrange
    chip_id = "test_chip_003"
    nonexistent_qubit_id = "Q99"

    chip = ChipDocument(
        chip_id=chip_id,
        username=TEST_USERNAME,
        size=1,
        qubits={"Q0": create_test_qubit("Q0")},
        system_info=system_info,
    )
    chip.insert()

    # Act & Assert
    with pytest.raises(ValueError, match=f"Qubit {nonexistent_qubit_id} not found"):
        chip.update_qubit(nonexistent_qubit_id, create_test_qubit(nonexistent_qubit_id))


def test_find_chip_by_username(system_info: SystemInfoModel) -> None:
    """Test finding chips by username."""
    # Arrange
    username1 = "user1"
    username2 = "user2"

    chips_data = [
        ("chip_user1_a", username1),
        ("chip_user1_b", username1),
        ("chip_user2", username2),
    ]

    # Create chips with different usernames
    for chip_id, username in chips_data:
        chip = ChipDocument(
            chip_id=chip_id,
            username=username,
            system_info=system_info,
        )
        chip.insert()

    # Act & Assert
    user1_chips = ChipDocument.find(ChipDocument.username == username1).to_list()
    assert len(user1_chips) == 2, f"Should find 2 chips for {username1}"
    assert all(
        chip.username == username1 for chip in user1_chips
    ), f"All chips should belong to {username1}"

    chip_ids = {chip.chip_id for chip in user1_chips}
    assert "chip_user1_a" in chip_ids, "Should contain chip_user1_a"
    assert "chip_user1_b" in chip_ids, "Should contain chip_user1_b"

    user2_chips = ChipDocument.find(ChipDocument.username == username2).to_list()
    assert len(user2_chips) == 1, f"Should find 1 chip for {username2}"
    assert user2_chips[0].chip_id == "chip_user2", "Should be chip_user2"
    assert user2_chips[0].username == username2, f"Username should be {username2}"


def test_delete_chip(system_info: SystemInfoModel) -> None:
    """Test deleting a chip document."""
    # Arrange
    chip_id = "chip_to_delete"

    chip = ChipDocument(
        chip_id=chip_id,
        username=TEST_USERNAME,
        system_info=system_info,
    )
    chip.insert()

    # Act & Assert - Verify it exists before deletion
    found_chip = ChipDocument.find_one(ChipDocument.chip_id == chip_id).run()
    assert found_chip is not None, f"Chip with id '{chip_id}' should exist before deletion"
    assert found_chip.chip_id == chip_id, "Found chip should have correct ID"

    # Delete the chip
    found_chip.delete()

    # Verify it's deleted
    deleted_chip = ChipDocument.find_one(ChipDocument.chip_id == chip_id).run()
    assert deleted_chip is None, f"Chip with id '{chip_id}' should not exist after deletion"
