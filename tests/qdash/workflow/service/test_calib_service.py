"""Tests for CalibService.

These tests verify the CalibService API and helper functions for custom calibration flows.
"""

import pytest
from unittest.mock import MagicMock, patch

from qdash.workflow.service.calib_service import (
    CalibService,
    finish_calibration,
    get_session,
    init_calibration,
)
from qdash.workflow.service.context import clear_current_session


class MockExecutionManager:
    """Mock ExecutionManager for testing."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.calib_data_path = kwargs.get("calib_data_path", "")
        self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()
        self.tags = kwargs.get("tags", [])
        self.completed = False

    def save(self):
        return self

    def start_execution(self):
        return self

    def update_execution_status_to_running(self):
        return self

    def complete_execution(self):
        self.completed = True
        return self

    def fail_execution(self):
        return self

    def reload(self):
        return self


class MockSession:
    """Mock quantum session for testing."""

    def __init__(self, *args, **kwargs):
        self.name = "fake"

    def connect(self):
        pass


class MockGitHubIntegration:
    """Mock GitHubIntegration for testing."""

    def __init__(self, *args, **kwargs):
        pass


class MockExecutionLockDocument:
    """Mock ExecutionLockDocument for testing."""

    @classmethod
    def get_lock_status(cls, project_id: str | None = None):
        return False

    @classmethod
    def lock(cls, project_id: str | None = None):
        pass

    @classmethod
    def unlock(cls, project_id: str | None = None):
        pass


@pytest.fixture(autouse=True)
def clear_session_state():
    """Clear session state before and after each test."""
    import qdash.workflow.service.calib_service as session_module

    # Clear before test
    session_module._current_session = None
    clear_current_session()

    yield

    # Clear after test
    session_module._current_session = None
    clear_current_session()


@pytest.fixture
def mock_flow_session_deps(monkeypatch):
    """Fixture to mock CalibService dependencies."""
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.ExecutionManager",
        MockExecutionManager,
    )
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.create_backend",
        lambda **kwargs: MockSession(),
    )
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.GitHubIntegration",
        MockGitHubIntegration,
    )
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.ExecutionLockDocument",
        MockExecutionLockDocument,
    )


class TestCalibServiceInitialization:
    """Test CalibService initialization and basic setup."""

    def test_flow_session_attributes(self, mock_flow_session_deps):
        """Test that CalibService initializes with correct attributes."""
        # Create session with qids (required parameter)
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0", "1"],
            backend_name="fake",
        )

        # Verify attributes
        assert session.username == "test_user"
        assert session.execution_id == "20240101-001"
        assert session.chip_id == "chip_1"
        assert session.backend_name == "fake"
        assert session.qids == ["0", "1"]
        assert session.execution_manager is not None
        assert session.backend is not None

    def test_flow_session_default_tags(self, mock_flow_session_deps):
        """Test that default tags are set correctly."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
            tags=["python_flow"],  # Explicitly pass tags
        )

        assert "python_flow" in session.execution_manager.tags


class TestCalibServiceParameterManagement:
    """Test parameter get/set operations."""

    def test_set_and_get_parameter(self, mock_flow_session_deps):
        """Test setting and getting parameters."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
        )

        # Set parameter
        session.set_parameter("0", "qubit_frequency", 5.0)

        # Get parameter
        freq = session.get_parameter("0", "qubit_frequency")
        assert freq == 5.0

    def test_get_nonexistent_parameter(self, mock_flow_session_deps):
        """Test getting a parameter that doesn't exist."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
        )

        # Get nonexistent parameter
        result = session.get_parameter("0", "nonexistent")
        assert result is None


class TestGlobalSessionHelpers:
    """Test global session helper functions."""

    def test_init_and_get_session(self, mock_flow_session_deps):
        """Test init_calibration and get_session."""
        # Initialize session with qids
        session1 = init_calibration(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0", "1"],
        )

        # Get session
        session2 = get_session()

        assert session1 is session2

    def test_get_session_without_init(self):
        """Test that get_session raises error when no session exists."""
        with pytest.raises(RuntimeError, match="No active calibration session"):
            get_session()

    def test_finish_calibration(self, mock_flow_session_deps, monkeypatch):
        """Test finish_calibration helper."""
        # Mock Prefect logger to avoid context error
        mock_logger = MagicMock()
        monkeypatch.setattr(
            "qdash.workflow.service.calib_service.get_run_logger",
            lambda: mock_logger,
        )

        # Initialize and finish
        session = init_calibration(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
        )

        finish_calibration()

        assert session.execution_manager.completed is True
