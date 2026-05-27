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

    def start(self):
        return self

    def complete(self):
        self.completed = True
        return self

    def fail(self):
        return self

    def reload(self):
        return self

    def merge_calib_data(self, calib_data):
        for qid, params in calib_data.qubit.items():
            self.calib_data.qubit.setdefault(qid, {}).update(params)
        for qid, params in calib_data.coupling.items():
            self.calib_data.coupling.setdefault(qid, {}).update(params)
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

    def __init__(self, config, github_integration=None, snapshot_loader=None):
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
        self._execution_service.complete()

    def fail(self):
        self._execution_service.fail()


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
    session_module._current_session = None  # type: ignore[attr-defined]
    clear_current_session()

    yield

    # Clear after test
    session_module._current_session = None  # type: ignore[attr-defined]
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

        assert session.execution_service is not None
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

    def test_sync_backend_params_filters_configured_push_files_to_touched_files(
        self,
        monkeypatch,
    ):
        """Only configured params files touched by this calibration should be batch-pushed."""
        from qdash.workflow.service.github import GitHubPushConfig

        class FakeUpdater:
            def update(self, qid, params):
                assert qid == "0"
                assert params == {"t1": {"value": 12.0}}
                return {"t1.yaml"}

        orchestrator = MagicMock()
        orchestrator._execution_service = MockExecutionService()
        orchestrator._execution_service.calib_data.qubit = {
            "0": {"t1": {"value": 12.0}},
        }
        orchestrator._backend = MagicMock()

        session = CalibService.__new__(CalibService)
        session.chip_id = "chip_1"
        session._orchestrator = orchestrator
        session.github_push_config = GitHubPushConfig(
            params_file_names=["t1.yaml", "t2_echo.yaml"],
        )

        monkeypatch.setattr(
            "qdash.workflow.service.calib_service.get_params_updater",
            lambda backend, chip_id: FakeUpdater(),
        )
        logger = MagicMock()

        session._sync_backend_params_before_push(logger)

        assert session.github_push_config.params_file_names == ["t1.yaml"]
        logger.info.assert_called_once()

    def test_sync_backend_params_keeps_touched_files_when_already_updated(
        self,
        monkeypatch,
    ):
        """Task-time params updates should still be batch-pushed on finish."""
        from qdash.workflow.service.github import GitHubPushConfig

        class FakeUpdater:
            def update(self, qid, params):
                assert qid == "0"
                assert params == {"t1": {"value": 12.0}}
                return set()

        orchestrator = MagicMock()
        orchestrator._execution_service = MockExecutionService()
        orchestrator._execution_service.calib_data.qubit = {
            "0": {"t1": {"value": 12.0}},
        }
        orchestrator._backend = MagicMock()

        session = CalibService.__new__(CalibService)
        session.chip_id = "chip_1"
        session._orchestrator = orchestrator
        session.github_push_config = GitHubPushConfig(
            params_file_names=["t1.yaml", "t2_echo.yaml"],
        )

        monkeypatch.setattr(
            "qdash.workflow.service.calib_service.get_params_updater",
            lambda backend, chip_id: FakeUpdater(),
        )
        monkeypatch.setattr(
            "qdash.workflow.engine.params_updater.ConfigLoader.load_workflow",
            lambda: {
                "params_updater": {
                    "parameter_file_map": {
                        "t1": "t1.yaml",
                        "t2_echo": "t2_echo.yaml",
                    },
                },
            },
        )
        logger = MagicMock()

        session._sync_backend_params_before_push(logger)

        assert session.github_push_config.params_file_names == ["t1.yaml"]
        logger.info.assert_called_once()

    def test_merge_task_result_calib_data_before_push_loads_completed_outputs(
        self,
        monkeypatch,
    ):
        """Parent sessions should rebuild calib_data from isolated child task results."""
        from qdash.datamodel.task import ParameterModel, TaskTypes

        class FakeFinder:
            def sort(self, sort):
                return self

            def run(self):
                return [
                    MagicMock(
                        qid="0",
                        task_type=TaskTypes.QUBIT,
                        task_id="task-1",
                        output_parameters={"control_amplitude": {"value": 0.25}},
                    )
                ]

        monkeypatch.setattr(
            "qdash.dbmodel.task_result_history.TaskResultHistoryDocument.find",
            lambda query: FakeFinder(),
        )

        orchestrator = MagicMock()
        orchestrator._execution_service = MockExecutionService()

        session = CalibService.__new__(CalibService)
        session.project_id = "test_project"
        session.execution_id = "exec-1"
        session._orchestrator = orchestrator

        session._merge_task_result_calib_data_before_push(MagicMock())

        execution_service = session.execution_service
        assert execution_service is not None
        merged = execution_service.calib_data.qubit["0"]["control_amplitude"]
        assert isinstance(merged, ParameterModel)
        assert merged.value == 0.25


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

        assert session.execution_service is not None
        assert session.execution_service.completed is True  # type: ignore[attr-defined]
