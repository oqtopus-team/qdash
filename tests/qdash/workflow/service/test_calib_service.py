"""Tests for CalibService.

These tests verify the CalibService API and helper functions for custom calibration flows.
"""

import re
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service.calib_service import (
    CalibService,
    finish_calibration,
    get_session,
    init_calibration,
)
from qdash.workflow.service.session_context import clear_current_session
from qdash.workflow.service.steps import Step
from qdash.workflow.service.targets import QubitTargets


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

    def __init__(self, locked: bool = False, owner: str | None = None) -> None:
        self.locked = locked
        self.owner = owner
        self.try_lock_calls: list[str | None] = []
        self.unlock_calls: list[str | None] = []

    def is_locked(self, project_id: str) -> bool:
        return self.locked

    def try_lock(
        self,
        project_id: str,
        execution_id: str | None = None,
        chip_id: str = "",
        resources: tuple[str, ...] = (),
        exclusive: bool = True,
    ) -> bool:
        self.try_lock_calls.append(execution_id)
        if self.locked and (execution_id is None or self.owner != execution_id):
            return False
        self.locked = True
        self.owner = execution_id
        return True

    def lock(self, project_id: str, execution_id: str | None = None) -> None:
        self.locked = True
        self.owner = execution_id

    def unlock(self, project_id: str, execution_id: str | None = None) -> None:
        self.unlock_calls.append(execution_id)
        if execution_id is not None and execution_id != self.owner:
            return
        self.locked = False
        self.owner = None


class MockUserRepository:
    """Mock UserRepository for testing."""

    def get_default_project_id(self, username: str) -> str | None:
        # Return None so tests must provide project_id explicitly
        return None


class FakeExecutionRepository:
    """Fake MongoExecutionRepository recording claim_scheduled_execution calls."""

    def __init__(self, claimed_execution_id: str | None) -> None:
        """Store the execution id this fake should return when a claim is attempted."""
        self.claimed_execution_id = claimed_execution_id
        self.calls: list[dict[str, str]] = []

    def claim_scheduled_execution(self, *, project_id: str, flow_run_id: str) -> str | None:
        """Record the call and return the pre-configured claimed execution id."""
        self.calls.append({"project_id": project_id, "flow_run_id": flow_run_id})
        return self.claimed_execution_id


class FakeExecutionCounterRepository:
    """Fake ExecutionCounterRepository returning a fixed next index without touching Mongo."""

    def __init__(self, next_index: int) -> None:
        """Store the fixed index this fake should return from get_next_index."""
        self.next_index = next_index

    def get_next_index(self, date: str, username: str, chip_id: str, project_id: str | None) -> int:
        """Return the pre-configured next index."""
        return self.next_index

    def get_dates_for_chip(self, project_id: str, chip_id: str) -> list[str]:
        """Return an empty list; unused by these tests."""
        return []


def _stub_prefect_flow_run_context(monkeypatch: pytest.MonkeyPatch, flow_run_id: str) -> None:
    """Register a fake prefect.context module exposing a flow run with the given id."""
    monkeypatch.setitem(
        sys.modules,
        "prefect.context",
        SimpleNamespace(
            get_run_context=lambda: SimpleNamespace(flow_run=SimpleNamespace(id=flow_run_id))
        ),
    )


@dataclass
class BoomStep(Step):
    """Step whose execute() always raises, to exercise the pipeline-abort logging path."""

    @property
    def name(self) -> str:
        """Return a fixed step name for identification."""
        return "boom"

    def execute(self, service: Any, targets: Any, ctx: Any) -> Any:
        """Raise a RuntimeError to simulate a step failing mid-pipeline."""
        raise RuntimeError("boom")


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

    def test_initialize_adopts_claimed_scheduled_execution(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo, monkeypatch
    ):
        """A scheduled execution claimed by flow_run_id is adopted as the session's execution_id."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id="20240101-777")
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)

        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
        )

        assert session.execution_id == "20240101-777"
        assert session.note is not None
        assert session.note["flow_run_id"] == "flow-run-9"
        assert fake_repo.calls == [{"project_id": "test_project", "flow_run_id": "flow-run-9"}]

    def test_initialize_generates_execution_id_when_nothing_claimed(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo, monkeypatch
    ):
        """With no scheduled execution to claim, _initialize falls back to generate_execution_id."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id=None)
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)
        fake_counter_repo = FakeExecutionCounterRepository(next_index=7)

        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
            counter_repo=fake_counter_repo,
        )

        assert fake_repo.calls == [{"project_id": "test_project", "flow_run_id": "flow-run-9"}]
        assert session.execution_id is not None
        assert re.fullmatch(r"\d{8}-007", session.execution_id)

    @pytest.mark.parametrize("skip_execution", [False, True])
    def test_initialize_adopts_a_lock_claimed_by_the_api_for_this_execution(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch, skip_execution
    ):
        """A lock the API claimed for the execution being claimed is adopted, not contested."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner="20240101-777")

        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=lock_repo,
            user_repo=mock_user_repo,
            skip_execution=skip_execution,
            counter_repo=FakeExecutionCounterRepository(next_index=7),
        )

        assert session.execution_id == "20240101-777"
        assert session._lock_acquired is True
        assert lock_repo.try_lock_calls == ["20240101-777"]
        assert lock_repo.owner == "20240101-777"
        assert session.skip_execution is False
        assert session._orchestrator is not None
        assert session._orchestrator.config.skip_execution is False

    @pytest.mark.parametrize("skip_execution", [False, True])
    def test_initialize_refuses_a_lock_owned_by_another_execution(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch, skip_execution
    ):
        """A lock owned by a different execution still blocks the session."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner="20240101-111")

        with pytest.raises(RuntimeError, match="Calibration is already running"):
            CalibService(
                username="test_user",
                chip_id="chip_1",
                qids=["0"],
                project_id="test_project",
                lock_repo=lock_repo,
                user_repo=mock_user_repo,
                skip_execution=skip_execution,
                counter_repo=FakeExecutionCounterRepository(next_index=7),
            )

        assert lock_repo.owner == "20240101-111"

    @pytest.mark.parametrize("skip_execution", [False, True])
    def test_initialize_refuses_an_unowned_lock(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch, skip_execution
    ):
        """A held lock with no recorded owner is not adopted either."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner=None)

        with pytest.raises(RuntimeError, match="Calibration is already running"):
            CalibService(
                username="test_user",
                chip_id="chip_1",
                qids=["0"],
                project_id="test_project",
                lock_repo=lock_repo,
                user_repo=mock_user_repo,
                skip_execution=skip_execution,
                counter_repo=FakeExecutionCounterRepository(next_index=7),
            )

    @pytest.mark.parametrize("terminal", ["complete", "fail", "cancel"])
    def test_api_wrapper_finalizes_its_adopted_execution_and_releases_lock(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch, terminal
    ):
        """The UI's parent row must reach a terminal state when its pipeline ends."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner="20240101-777")
        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            skip_execution=True,
            lock_repo=lock_repo,
            user_repo=mock_user_repo,
            counter_repo=FakeExecutionCounterRepository(next_index=7),
        )
        execution_service = MagicMock()
        session.execution_service = execution_service
        monkeypatch.setattr(session, "_finalize_stale_running_tasks", MagicMock())
        monkeypatch.setattr(session, "_finalize_tasks_on_cancel", MagicMock())

        if terminal == "complete":
            session.finish_calibration(update_chip_history=False, push_to_github=False)
        elif terminal == "fail":
            session.fail_calibration("measurement failed")
        else:
            session.cancel_calibration()

        getattr(execution_service.reload.return_value, terminal).assert_called_once()
        assert lock_repo.locked is False
        assert session._lock_acquired is False

    @pytest.mark.parametrize("execution_id", [None, "parent-execution"])
    def test_isolated_worker_does_not_claim_or_finalize_parent_execution(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch, execution_id
    ):
        """Workers borrowing a parent's execution must not take over its lifecycle."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id="20240101-777")
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)
        lock_repo = MockExecutionLockRepository(locked=True, owner="parent-execution")
        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            execution_id=execution_id,
            skip_execution=True,
            use_lock=False,
            lock_repo=lock_repo,
            user_repo=mock_user_repo,
            counter_repo=FakeExecutionCounterRepository(next_index=7),
        )
        execution_service = MagicMock()
        session.execution_service = execution_service

        session.finish_calibration(update_chip_history=False, push_to_github=False)
        session.fail_calibration()
        session.cancel_calibration()

        assert fake_repo.calls == []
        assert session.skip_execution is True
        assert lock_repo.try_lock_calls == []
        assert lock_repo.owner == "parent-execution"
        assert lock_repo.locked is True
        execution_service.reload.assert_not_called()

    def test_wrapper_without_api_execution_keeps_skipping_execution_creation(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch
    ):
        """Scheduled or direct pipelines can still run without a pre-created parent row."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id=None)
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)
        lock_repo = MockExecutionLockRepository()
        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            skip_execution=True,
            lock_repo=lock_repo,
            user_repo=mock_user_repo,
            counter_repo=FakeExecutionCounterRepository(next_index=7),
        )

        assert session.skip_execution is True
        assert session.execution_id is not None
        assert re.fullmatch(r"\d{8}-007", session.execution_id)
        assert lock_repo.owner == session.execution_id
        session.finish_calibration(update_chip_history=False, push_to_github=False)
        assert lock_repo.locked is False

    def test_initialize_takes_a_free_lock_itself(
        self, mock_flow_session_deps, mock_user_repo, monkeypatch
    ):
        """Runs that never went through the API, such as cron schedules, lock here."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository()

        session = CalibService(
            username="test_user",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=lock_repo,
            user_repo=mock_user_repo,
        )

        assert lock_repo.try_lock_calls == ["20240101-777"]
        assert lock_repo.locked is True
        assert lock_repo.owner == session.execution_id


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


class TestRunPipelineFailureLogging:
    """Test that _run_pipeline logs the abort reason and re-raises on step failure."""

    def test_run_pipeline_logs_and_reraises_on_step_failure(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo
    ):
        """A step raising during execute() propagates after the abort is logged."""
        session = CalibService(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            qids=["0"],
            project_id="test_project",
            lock_repo=mock_lock_repo,
            user_repo=mock_user_repo,
        )

        with pytest.raises(RuntimeError, match="boom"):
            session._run_pipeline(QubitTargets(["0"]), [BoomStep()])


@pytest.fixture
def pipeline_execution_env(mock_flow_session_deps, monkeypatch):
    """Exercise real pipeline/strategy lifecycle without hardware or database I/O."""
    records = []
    lock = MockExecutionLockRepository(locked=True, owner="exec-reserved")
    claims = MagicMock(side_effect=["exec-reserved", None])
    monkeypatch.setattr(CalibService, "_read_flow_run_id_from_context", lambda self: "flow-1")
    monkeypatch.setattr(
        "qdash.repository.MongoExecutionRepository",
        lambda: SimpleNamespace(claim_scheduled_execution=claims),
    )

    class RecordingOrchestrator(MockCalibOrchestrator):
        def initialize(self):
            super().initialize()
            record = SimpleNamespace(config=self.config, status="running")
            records.append(record)
            for method, status in (
                ("complete", "completed"),
                ("fail", "failed"),
                ("cancel", "cancelled"),
            ):

                def close(status=status):
                    assert lock.locked  # No stage may release the pipeline lock.
                    record.status = status
                    return self._execution_service

                setattr(self._execution_service, method, close)

    monkeypatch.setattr(
        "qdash.workflow.service.calib_service.CalibOrchestrator", RecordingOrchestrator
    )
    for method in (
        "record_stage_result",
        "_finalize_stale_running_tasks",
        "_finalize_tasks_on_cancel",
        "_update_chip_history",
        "_push_to_github_if_configured",
    ):
        monkeypatch.setattr(CalibService, method, MagicMock())
    schedule = SimpleNamespace(
        stages=[SimpleNamespace(box_type="A", parallel_groups=[["0", "1"]])],
        steps=[SimpleNamespace(box_type="A", parallel_qids=["0", "1"], step_index=0)],
        total_steps=1,
        metadata={"strategy": "test"},
    )
    scheduler = MagicMock()
    scheduler.generate_from_mux.return_value = schedule
    scheduler.generate_synchronized_from_mux.return_value = schedule
    scheduler.generate_simultaneous_spectroscopy_batches_from_mux.return_value = schedule
    monkeypatch.setattr("qdash.workflow.service.strategy.OneQubitScheduler", lambda **kw: scheduler)
    return SimpleNamespace(records=records, lock=lock, claims=claims)


@pytest.mark.parametrize("skip_execution", [False, True])
@pytest.mark.parametrize(
    "mode", ["synchronized", "scheduled", "serial", "simultaneous_spectroscopy"]
)
def test_pipeline_owns_one_execution_per_calibration_step(
    pipeline_execution_env, monkeypatch, skip_execution, mode
):
    from qdash.workflow.service.steps import FilterByStatus, OneQubitCheck, OneQubitFineTune

    env = pipeline_execution_env
    worker_ids = []

    def run_workers(*, tasks, qids=None, mux_groups=None, session_config=None):
        session = get_session()
        assert env.lock.owner == "exec-reserved"
        assert all(record.status == "completed" for record in env.records[:-1])
        worker_ids.append(
            session_config["execution_id"] if session_config else session.execution_id
        )
        return {"0": {"status": "success"}, "1": {"status": "success"}}

    for method in (
        "run_qubit_calibrations_parallel",
        "run_mux_calibrations_parallel",
        "_calibrate_mux_qubits",
    ):
        monkeypatch.setattr(f"qdash.workflow.service.strategy.{method}", run_workers)
    monkeypatch.setattr(
        CalibService, "execute_task_batch", lambda self, name, qids: run_workers(tasks=[name])
    )
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        flow_name="one",
        skip_execution=skip_execution,
        enable_github=False,
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
    )

    session.run(
        QubitTargets(["0", "1"]),
        steps=[
            OneQubitCheck(mode=mode, tasks=["CheckRabi"]),
            FilterByStatus(),
            OneQubitFineTune(mode=mode, tasks=["CheckRamsey"]),
        ],
    )

    assert len(env.records) == 2
    first, second = env.records
    assert first.config.execution_id == "exec-reserved"
    assert second.config.execution_id != first.config.execution_id
    assert worker_ids == [first.config.execution_id, second.config.execution_id]
    assert [record.status for record in env.records] == ["completed", "completed"]
    assert [record.config.flow_name for record in env.records] == [
        "one_one_qubit_check",
        "one_one_qubit_fine_tune",
    ]
    assert [record.config.note["step_index"] for record in env.records] == [1, 3]
    assert all(record.config.note["flow_run_id"] == "flow-1" for record in env.records)
    assert all(record.config.skip_execution is False for record in env.records)
    assert env.lock.try_lock_calls == ["exec-reserved"]
    assert env.lock.unlock_calls == ["exec-reserved"]
    assert env.lock.locked is False
    assert session.flow_name == "one"
    with pytest.raises(RuntimeError, match="No active"):
        get_session()


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("transform_failure", [False, True])
def test_pipeline_failure_preserves_completed_steps(
    pipeline_execution_env, cancel, transform_failure
):
    from qdash.workflow.service.steps.base import TransformStep

    env = pipeline_execution_env

    class CancelledRun(BaseException):
        pass

    class FirstStep(BoomStep):
        def execute(self, service, targets, ctx):
            return ctx

    class FailureStep(BoomStep):
        def execute(self, service, targets, ctx):
            assert env.lock.locked
            assert env.records[0].status == "completed"
            raise CancelledRun() if cancel else RuntimeError("boom")

    class FailureTransform(FailureStep, TransformStep):
        pass

    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        enable_github=False,
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
    )
    with pytest.raises(CancelledRun if cancel else RuntimeError):
        session.run(
            QubitTargets(["0"]),
            steps=[
                FirstStep(),
                FailureTransform() if transform_failure else FailureStep(),
            ],
        )
    expected = (
        ["completed"] if transform_failure else ["completed", "cancelled" if cancel else "failed"]
    )
    assert [record.status for record in env.records] == expected
    assert env.lock.locked is False


@pytest.mark.parametrize("skip_execution", [False, True])
def test_single_step_without_api_reservation_creates_one_execution(
    pipeline_execution_env, monkeypatch, skip_execution
):
    from qdash.workflow.service.steps import CustomOneQubit

    env = pipeline_execution_env
    env.lock.unlock("project-1")
    env.claims.side_effect = [None]
    worker = MagicMock(return_value={"0": {"status": "success"}})
    monkeypatch.setattr(
        "qdash.workflow.service.strategy.run_qubit_calibrations_parallel",
        worker,
    )
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        enable_github=False,
        skip_execution=skip_execution,
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
    )
    session.run(QubitTargets(["0"]), steps=[CustomOneQubit(tasks=["CheckRabi"])])

    assert len(env.records) == 1
    assert env.records[0].status == "completed"
    assert env.records[0].config.skip_execution is False
    assert (
        worker.call_args.kwargs["session_config"]["execution_id"]
        == env.records[0].config.execution_id
    )
    assert env.lock.locked is False


def test_two_qubit_steps_reuse_their_pipeline_execution(pipeline_execution_env, monkeypatch):
    from qdash.workflow.service.steps import CustomTwoQubit, TwoQubitCalibration

    env = pipeline_execution_env
    scheduler = MagicMock()
    scheduler.generate.return_value = SimpleNamespace(parallel_groups=[[("0", "1")]])
    monkeypatch.setattr("qdash.workflow.engine.CRScheduler", lambda *a, **kw: scheduler)
    worker = MagicMock(return_value={"0-1": {"status": "success"}})
    monkeypatch.setattr(
        "qdash.workflow.service._internal.scheduling_tasks.run_coupling_calibrations_parallel",
        worker,
    )
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        backend_name="fake",
        enable_github=False,
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
        default_run_parameters={"interval": {"value": 1024, "value_type": "int"}},
    )
    session.run(
        QubitTargets(["0", "1"]),
        steps=[
            CustomTwoQubit(tasks=["CheckCrossResonance"]),
            TwoQubitCalibration(),
        ],
    )
    assert len(env.records) == 2
    configs = [call.kwargs["session_config"] for call in worker.call_args_list]
    assert [config["execution_id"] for config in configs] == [
        record.config.execution_id for record in env.records
    ]
    assert all(config["backend_name"] == "fake" for config in configs)
    assert all(
        config["default_run_parameters"] == session.default_run_parameters for config in configs
    )
    assert [record.status for record in env.records] == ["completed", "completed"]
    assert env.lock.locked is False


@pytest.fixture
def pipeline_wiring(tmp_path, monkeypatch):
    from qdash.common import execution_resources

    path = tmp_path / "chip-1" / "config" / "wiring.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "chip-1:\n"
        + "".join(
            f"  - mux: {mux}\n    ctrl: [C{mux}-1]\n    read_out: R{mux}-1\n" for mux in range(4)
        )
    )
    monkeypatch.setattr(execution_resources, "resolve_config_base_path", lambda: tmp_path)


def test_pipeline_plan_includes_later_configuration_and_schedule(pipeline_wiring):
    from qdash.workflow.service.pipeline_resources import plan_pipeline_resources
    from qdash.workflow.service.steps import ConfigureAll, OneQubitCheck, SetCRSchedule

    scope = plan_pipeline_resources(
        "chip-1",
        QubitTargets(["0"]),
        [OneQubitCheck(), ConfigureAll(mux_ids=[1]), SetCRSchedule(schedule=[[("8", "12")]])],
    )
    assert not scope.exclusive
    assert {r for r in scope.resources if r.startswith("mux:")} == {
        "mux:0",
        "mux:1",
        "mux:2",
        "mux:3",
    }


def test_unknown_step_plan_is_chip_exclusive(pipeline_wiring):
    from qdash.workflow.service.pipeline_resources import plan_pipeline_resources

    scope = plan_pipeline_resources("chip-1", QubitTargets(["0"]), [BoomStep()])
    assert scope.exclusive


def test_pipeline_blocks_on_later_step_resources_before_running_any_step(
    pipeline_execution_env,
    pipeline_wiring,
    monkeypatch,
):
    from qdash.repository.inmemory.execution_lock import InMemoryExecutionLockRepository
    from qdash.workflow.service.steps import ConfigureAll, CustomOneQubit

    repo = InMemoryExecutionLockRepository()
    assert repo.try_lock("project-1", "other-run", "chip-1", ("mux:1",), False)
    run_step = MagicMock()
    monkeypatch.setattr(CustomOneQubit, "execute", run_step)
    session = CalibService(
        "alice", "chip-1", project_id="project-1", enable_github=False, lock_repo=repo
    )
    with pytest.raises(RuntimeError, match="already running"):
        session.run(QubitTargets(["0"]), [CustomOneQubit(), ConfigureAll(mux_ids=[1])])
    run_step.assert_not_called()
    assert repo.is_locked("project-1")
    assert not repo.try_lock("project-1", "third", "chip-1", ("mux:1",), False)


@pytest.mark.parametrize("fail", [False, True])
def test_pipeline_retains_whole_plan_and_releases_its_original_owner(
    pipeline_execution_env,
    pipeline_wiring,
    monkeypatch,
    fail,
):
    from qdash.repository.inmemory.execution_lock import InMemoryExecutionLockRepository
    from qdash.workflow.service.steps import ConfigureAll, CustomOneQubit

    repo = InMemoryExecutionLockRepository()
    assert repo.try_lock("project-1", "exec-reserved", "chip-1", ("mux:0",), False)
    assert repo.try_lock("project-1", "other-chip", "chip-2", ("mux:0",), False)
    seen = []

    def first(self, service, targets, ctx):
        seen.append(service.execution_id)
        assert not repo.try_lock("project-1", "intruder", "chip-1", ("mux:1",), False)
        return ctx

    def second(self, service, targets, ctx):
        seen.append(service.execution_id)
        assert not repo.try_lock("project-1", "intruder", "chip-1", ("mux:0",), False)
        assert not repo.try_lock("project-1", "intruder", "chip-1", ("mux:1",), False)
        if fail:
            raise RuntimeError("second step failed")
        return ctx

    monkeypatch.setattr(CustomOneQubit, "execute", first)
    monkeypatch.setattr(ConfigureAll, "execute", second)
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        enable_github=False,
        lock_repo=repo,
        counter_repo=FakeExecutionCounterRepository(2),
    )
    if fail:
        with pytest.raises(RuntimeError, match="second step failed"):
            session.run(QubitTargets(["0"]), [CustomOneQubit(), ConfigureAll(mux_ids=[1])])
    else:
        session.run(QubitTargets(["0"]), [CustomOneQubit(), ConfigureAll(mux_ids=[1])])
    assert seen[0] == "exec-reserved"
    assert seen[1] != seen[0]
    assert repo.try_lock("project-1", "next-run", "chip-1", (), True)
    assert not repo.try_lock("project-1", "other", "chip-2", ("mux:0",), False)


def test_pipeline_rejects_unplanned_targets_before_later_hardware_step(
    pipeline_execution_env,
    pipeline_wiring,
    monkeypatch,
):
    from qdash.workflow.service.steps import CustomOneQubit, SetCRSchedule

    def change_targets(self, service, targets, ctx):
        ctx.candidate_qids = ["12"]  # The declared schedule only reserved MUX 0.
        return ctx

    run_step = MagicMock()
    monkeypatch.setattr(SetCRSchedule, "execute", change_targets)
    monkeypatch.setattr(CustomOneQubit, "execute", run_step)
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        enable_github=False,
        lock_repo=pipeline_execution_env.lock,
    )
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.run(QubitTargets(["0"]), [SetCRSchedule(schedule=[[("0", "1")]]), CustomOneQubit()])
    run_step.assert_not_called()
    assert not pipeline_execution_env.lock.locked


def test_task_and_isolated_worker_reject_unreserved_hardware(pipeline_wiring, monkeypatch):
    from qdash.common.execution_resources import resolve_execution_resource_scope
    from qdash.workflow.service._internal.scheduling_tasks import _create_isolated_session

    scope = resolve_execution_resource_scope("chip-1", {"qid": "0"})
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        use_lock=False,
        resource_scope=scope,
        enable_github=False,
    )
    orchestrator = MagicMock()
    session._orchestrator = orchestrator
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.execute_task("CheckRabi", "4")
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.execute_task_batch("CheckRabi", ["0", "4"])
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.execute_task(
            "ConfigureAll", "", {"ConfigureAll": {"run_parameters": {"mux_ids": {"value": [1]}}}}
        )
    orchestrator.run_task.assert_not_called()
    orchestrator.run_task_batch.assert_not_called()
    with pytest.raises(RuntimeError, match="outside the workflow"):
        _create_isolated_session(
            {
                "username": "alice",
                "chip_id": "chip-1",
                "project_id": "project-1",
                "execution_id": "child",
                "backend_name": "fake",
                "note": {
                    "hardware_reservation": {
                        "chip_id": scope.chip_id,
                        "resources": list(scope.resources),
                        "exclusive": False,
                    }
                },
            },
            ["4"],
        )


def test_pipeline_keeps_supplied_reservation_owner(pipeline_execution_env, monkeypatch):
    from qdash.workflow.service.steps import CustomOneQubit

    monkeypatch.setattr(CustomOneQubit, "execute", lambda self, service, targets, ctx: ctx)
    session = CalibService(
        "alice",
        "chip-1",
        project_id="project-1",
        enable_github=False,
        execution_id="exec-reserved",
        lock_repo=pipeline_execution_env.lock,
    )
    session.run(QubitTargets(["0"]), [CustomOneQubit()])
    assert pipeline_execution_env.lock.try_lock_calls == ["exec-reserved"]
    assert pipeline_execution_env.lock.unlock_calls == ["exec-reserved"]
    with pytest.raises(RuntimeError, match="No hardware reservation"):
        session.execute_task("CheckRabi", "0")
