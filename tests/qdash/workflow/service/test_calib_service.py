"""Tests for CalibService.

These tests verify the CalibService API and helper functions for custom calibration flows.
"""

from unittest.mock import MagicMock

import pytest
from qdash.workflow.service.calib_service import (
    CalibService,
    finish_calibration,
    get_session,
    init_calibration,
)
from qdash.workflow.service.session_context import clear_current_session


class MockExecutionService:
    """Mock ExecutionService for testing."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.calib_data_path = kwargs.get("calib_data_path", "")
        self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()
        self.tags = kwargs.get("tags", [])
        self.project_id = kwargs.get("project_id", "test_project")
        self.completed = False

    def save(self):
        return self

    def save_with_tags(self):
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

    @classmethod
    def create(cls, **kwargs):
        return cls(**kwargs)


class MockTaskContext:
    """Mock TaskSession for testing."""

    def __init__(self, *args, **kwargs):
        self.id = "mock-task-session-id"
        self.calib_data = type("obj", (object,), {"qubit": {"0": {}}, "coupling": {}})()
        self.state = MagicMock()
        self.state.calib_data = self.calib_data

    def save(self):
        pass


class MockBackend:
    """Mock backend for testing."""

    def __init__(self, *args, **kwargs):
        self.name = "fake"

    def connect(self):
        pass


class MockCalibOrchestrator:
    """Mock CalibOrchestrator for testing."""

    def __init__(self, config, github_integration=None):
        self.config = config
        self._initialized = False
        self._execution_service = MockExecutionService(tags=config.tags or [])
        self._task_context = MockTaskContext()
        self._backend = MockBackend()

    @property
    def execution_service(self):
        return self._execution_service

    @property
    def task_context(self):
        return self._task_context

    @property
    def backend(self):
        return self._backend

    @property
    def is_initialized(self):
        return self._initialized

    def initialize(self):
        self._initialized = True

    def complete(self, update_chip_history=True, export_note_to_file=False):
        self._execution_service.complete_execution()

    def fail(self):
        self._execution_service.fail_execution()


class MockGitHubIntegration:
    """Mock GitHubIntegration for testing."""

    def __init__(self, *args, **kwargs):
        pass

    @staticmethod
    def check_credentials():
        return False


class MockExecutionLockRepository:
    """Mock ExecutionLockRepository for testing."""

    def is_locked(self, project_id: str) -> bool:
        return False

    def lock(self, project_id: str) -> None:
        pass

    def unlock(self, project_id: str) -> None:
        pass


class MockUserRepository:
    """Mock UserRepository for testing."""

    def get_default_project_id(self, username: str) -> str | None:
        # Return None so tests must provide project_id explicitly
        return None


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
def mock_lock_repo():
    """Create a mock lock repository."""
    return MockExecutionLockRepository()


@pytest.fixture
def mock_user_repo():
    """Create a mock user repository."""
    return MockUserRepository()


@pytest.fixture
def mock_flow_session_deps(monkeypatch):
    """Fixture to mock CalibService dependencies."""
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.CalibOrchestrator",
        MockCalibOrchestrator,
    )
    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.GitHubIntegration",
        MockGitHubIntegration,
    )
    # Patch the repository imports where they are lazily imported in CalibService
    monkeypatch.setattr(
        "qdash.repository.MongoExecutionLockRepository",
        MockExecutionLockRepository,
    )
    monkeypatch.setattr(
        "qdash.repository.MongoUserRepository",
        MockUserRepository,
    )


class TestCalibServiceInitialization:
    """Test CalibService initialization and basic setup."""

    def test_flow_session_attributes(self, mock_flow_session_deps, mock_lock_repo, mock_user_repo):
        """Test that CalibService initializes with correct attributes."""
        # Create session with qids (required parameter)
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0", "1"],
            backend_name="fake",
            project_id="test_project",  # Required to avoid UserDocument lookup
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
        )

        # Verify attributes
        assert session.username == "test_user"
        assert session.execution_id == "20240101-001"
        assert session.chip_id == "chip_1"
        assert session.backend_name == "fake"
        assert session.qids == ["0", "1"]
        assert session.execution_service is not None
        assert session.backend is not None

    def test_flow_session_default_tags(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo
    ):
        """Test that default tags are set correctly."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
            tags=["python_flow"],  # Explicitly pass tags
            project_id="test_project",
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
        )

        assert "python_flow" in session.execution_service.tags


class TestCalibServiceParameterManagement:
    """Test parameter get/set operations."""

    def test_set_and_get_parameter(self, mock_flow_session_deps, mock_lock_repo, mock_user_repo):
        """Test setting and getting parameters."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
        )

        # Set parameter
        session.set_parameter("0", "qubit_frequency", 5.0)

        # Get parameter
        freq = session.get_parameter("0", "qubit_frequency")
        assert freq == 5.0

    def test_get_nonexistent_parameter(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo
    ):
        """Test getting a parameter that doesn't exist."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
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
            project_id="test_project",
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
            project_id="test_project",
        )

        finish_calibration()

        assert session.execution_service.completed is True
