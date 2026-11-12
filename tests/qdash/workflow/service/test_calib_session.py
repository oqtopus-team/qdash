"""Tests for the internal CalibSession lifecycle, reservation and worker policy."""

import asyncio
import re
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from qdash.common.mux_mapping import MuxMapping, MuxMappingSnapshot
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service._internal.lifecycle import (
    is_cancellation as _is_cancellation,
)
from qdash.workflow.service._internal.lifecycle import (
    is_external_termination as _is_external_termination,
)
from qdash.workflow.service._internal.session import (
    CalibSession,
    SessionRepositories,
    borrowed_session,
)
from qdash.workflow.service._internal.settings import (
    GitHubPolicy,
    ReservationScope,
    SessionSettings,
    WorkerLease,
    WorkerSpec,
)
from qdash.workflow.service.session_context import clear_current_session, get_session
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

    def fail(self, error_message=""):
        return self

    def cancel(self):
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
        self.disconnect = MagicMock()

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


def _settings(**overrides: Any) -> SessionSettings:
    """Session settings with test defaults; GitHub is off unless a test enables it."""
    values: dict[str, Any] = {
        "username": "test_user",
        "chip_id": "chip_1",
        "project_id": "test_project",
        "backend_name": "qubex",
        "github": GitHubPolicy.disabled(),
    }
    values.update(overrides)
    return SessionSettings(**values)


def _session(
    *,
    qids: list[str] | None = None,
    execution_id: str | None = None,
    lock_repo: Any = None,
    counter_repo: Any = None,
    **overrides: Any,
) -> CalibSession:
    """An owner session; ``qids`` initializes it the way a step's Execution opens."""
    session = CalibSession(
        _settings(**overrides),
        repositories=SessionRepositories(lock_repo=lock_repo, counter_repo=counter_repo),
    )
    session.execution_id = execution_id
    if qids is not None:
        session._initialize(qids)
    return session


def _worker(
    qids: list[str],
    *,
    execution_id: str = "20240101-001",
    reservation: Any = None,
    **overrides: Any,
) -> CalibSession:
    """A worker session borrowing ``execution_id``, initialized for ``qids``."""
    session = CalibSession(
        _settings(**overrides).for_worker(),
        lease=WorkerLease(
            execution_id=execution_id,
            reservation=ReservationScope.of(reservation) if reservation is not None else None,
        ),
        mux_mapping=MuxMapping.legacy(),
    )
    session._initialize(qids)
    return session


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

    def execute(self, session: Any, targets: Any, ctx: Any) -> Any:
        """Raise a RuntimeError to simulate a step failing mid-pipeline."""
        raise RuntimeError("boom")


@dataclass
class RaisingStep(Step):
    """Step that raises a caller-supplied exception, to exercise abort classification."""

    exc: BaseException = field(default_factory=lambda: RuntimeError("boom"))

    @property
    def name(self) -> str:
        """Return a fixed step name for identification."""
        return "raising"

    def execute(self, session: Any, targets: Any, ctx: Any) -> Any:
        """Raise the exception supplied at construction time."""
        raise self.exc


class CancelledRun(Exception):
    """Stand-in for prefect.exceptions.CancelledRun, which is matched by class name."""


class ExternalSignal(BaseException):
    """Stand-in for prefect.exceptions.ExternalSignal."""


class TerminationSignal(ExternalSignal):
    """Stand-in for prefect.exceptions.TerminationSignal."""


LEGACY_MAPPING = MuxMappingSnapshot.of(MuxMapping.legacy())
"""What an owner of a chip without a topology hands its workers."""


@pytest.fixture(autouse=True)
def chips_without_topology(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Store every chip of these tests as a legacy chip (no ``topology_id``).

    Only the chip document lookup is replaced: ``resolve_chip_mux_mapping``,
    the Qubex layout check and the scope checks still run, so sessions resolve
    the legacy mapping exactly as they do for such a chip in production. Tests
    about unusable topologies live in the MUX mapping test modules.
    """
    lookups: list[tuple[Any, ...]] = []

    def find_one(*args: Any, **kwargs: Any) -> Any:
        lookups.append(args)
        return SimpleNamespace(run=lambda: SimpleNamespace(topology_id=None))

    monkeypatch.setattr("qdash.dbmodel.chip.ChipDocument.find_one", find_one)
    return lookups


@pytest.fixture(autouse=True)
def clear_session_state():
    """Clear session state before and after each test."""
    clear_current_session()
    yield
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
    """Fixture to mock CalibSession dependencies."""
    monkeypatch.setattr(
        "qdash.workflow.service._internal.session.CalibOrchestrator",
        MockCalibOrchestrator,
    )
    monkeypatch.setattr(
        "qdash.workflow.service._internal.session.GitHubIntegration",
        MockGitHubIntegration,
    )
    # Patch the repository imports where they are lazily imported in CalibSession
    monkeypatch.setattr(
        "qdash.repository.MongoExecutionLockRepository",
        MockExecutionLockRepository,
    )
    monkeypatch.setattr(
        "qdash.repository.MongoUserRepository",
        MockUserRepository,
    )


class TestCalibSessionInitialization:
    """Owner and worker session initialization."""

    def test_owner_session_attributes(self, mock_flow_session_deps, mock_lock_repo):
        session = _session(execution_id="20240101-001", qids=["0", "1"], lock_repo=mock_lock_repo)

        assert session.username == "test_user"
        assert session.execution_id == "20240101-001"
        assert session.chip_id == "chip_1"
        assert session.backend_name == "qubex"
        assert session.qids == ["0", "1"]
        assert session.execution_service is not None
        assert session.backend is not None
        assert session._orchestrator is not None
        assert session._orchestrator.config.skip_execution is False

    def test_configuration_mode_is_applied_to_the_session_config(
        self, mock_flow_session_deps, mock_lock_repo
    ):
        session = _session(
            execution_id="20240101-001",
            qids=["0"],
            configuration_mode="ge-ef-fh",
            lock_repo=mock_lock_repo,
        )

        assert session.configuration_mode == "ge-ef-fh"
        assert session._orchestrator is not None
        assert session._orchestrator.config.configuration_mode == "ge-ef-fh"

    def test_resolved_configuration_mode_reaches_workers(
        self, mock_flow_session_deps, mock_lock_repo, monkeypatch
    ):
        """The backend's environment default is resolved once and inherited."""
        monkeypatch.setenv("QUBEX_CONFIGURATION_MODE", "ge-ef-cr")
        session = _session(execution_id="20240101-001", qids=["0"], lock_repo=mock_lock_repo)

        assert session.worker_spec().settings.configuration_mode == "ge-ef-cr"

    def test_worker_inherits_configuration_mode(self, mock_flow_session_deps):
        session = _worker(["0"], configuration_mode="ge-ef-fh")

        assert session.configuration_mode == "ge-ef-fh"
        assert session._orchestrator is not None
        assert session._orchestrator.config.configuration_mode == "ge-ef-fh"
        assert session._orchestrator.config.skip_execution is True

    def test_worker_resolves_writeback_like_its_parent(self, mock_flow_session_deps):
        """Per-task write-back defaults reach the worker; calls still decide for themselves."""
        from qdash.workflow.engine.orchestrator import CalibOrchestrator

        session = _worker(
            ["0"], task_defaults={"CheckRabi": {"update_calibration_parameters": False}}
        )

        assert session._orchestrator is not None
        resolve = CalibOrchestrator(
            session._orchestrator.config
        )._should_update_calibration_parameters
        assert resolve("CheckRabi", None) is False
        assert resolve("CheckRabi", {"update_calibration_parameters": True}) is True
        assert resolve("CheckT1", None) is True
        assert resolve("CheckT1", {"update_calibration_parameters": False}) is False

    def test_unknown_task_default_is_rejected_before_any_session(self):
        with pytest.raises(ValueError, match="CheckRabbi"):
            CalibSession(_settings(task_defaults={"CheckRabbi": {"run": {"shots": 1}}}))

    def test_session_tags_reach_the_execution(self, mock_flow_session_deps, mock_lock_repo):
        session = _session(
            execution_id="20240101-001",
            qids=["0"],
            tags=["python_flow"],
            lock_repo=mock_lock_repo,
        )

        assert session.execution_service is not None
        assert "python_flow" in session.execution_service.tags

    def test_initialize_adopts_claimed_scheduled_execution(
        self, mock_flow_session_deps, mock_lock_repo, monkeypatch
    ):
        """A scheduled execution claimed by flow_run_id is adopted as the session's execution_id."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id="20240101-777")
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)

        session = _session(qids=["0"], lock_repo=mock_lock_repo)

        assert session.execution_id == "20240101-777"
        assert session._orchestrator is not None
        assert (session._orchestrator.config.note or {})["flow_run_id"] == "flow-run-9"
        assert fake_repo.calls == [{"project_id": "test_project", "flow_run_id": "flow-run-9"}]

    def test_initialize_generates_execution_id_when_nothing_claimed(
        self, mock_flow_session_deps, mock_lock_repo, monkeypatch
    ):
        """With no scheduled execution to claim, _initialize falls back to generate_execution_id."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id=None)
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)

        session = _session(
            qids=["0"],
            lock_repo=mock_lock_repo,
            counter_repo=FakeExecutionCounterRepository(next_index=7),
        )

        assert fake_repo.calls == [{"project_id": "test_project", "flow_run_id": "flow-run-9"}]
        assert session.execution_id is not None
        assert re.fullmatch(r"\d{8}-007", session.execution_id)

    def test_initialize_adopts_a_lock_claimed_by_the_api_for_this_execution(
        self, mock_flow_session_deps, monkeypatch
    ):
        """A lock the API claimed for the execution being claimed is adopted, not contested."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner="20240101-777")

        session = _session(
            qids=["0"],
            lock_repo=lock_repo,
            counter_repo=FakeExecutionCounterRepository(next_index=7),
        )

        assert session.execution_id == "20240101-777"
        assert session._lock_acquired is True
        assert lock_repo.try_lock_calls == ["20240101-777"]
        assert lock_repo.owner == "20240101-777"
        assert session._orchestrator is not None
        assert session._orchestrator.config.skip_execution is False

    @pytest.mark.parametrize("owner", ["20240101-111", None])
    def test_initialize_refuses_a_lock_held_by_another_execution(
        self, mock_flow_session_deps, monkeypatch, owner
    ):
        """A lock owned by a different execution, or by no recorded owner, blocks the session."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner=owner)

        with pytest.raises(RuntimeError, match="Calibration is already running"):
            _session(
                qids=["0"],
                lock_repo=lock_repo,
                counter_repo=FakeExecutionCounterRepository(next_index=7),
            )

        assert lock_repo.owner == owner

    @pytest.mark.parametrize("terminal", ["complete", "fail", "cancel"])
    def test_owner_closes_its_adopted_execution_and_releases_lock(
        self, mock_flow_session_deps, monkeypatch, terminal
    ):
        """The UI's row must reach a terminal state when its owner ends."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository(locked=True, owner="20240101-777")
        session = _session(
            qids=["0"],
            lock_repo=lock_repo,
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
        backend = session.backend
        assert backend is not None
        cast("MagicMock", backend.disconnect).assert_called_once_with()
        if terminal == "fail":
            execution_service.reload.return_value.fail.assert_called_once_with("measurement failed")
        assert lock_repo.locked is False
        assert session._lock_acquired is False

    def test_worker_does_not_claim_lock_or_finalize_its_owners_execution(
        self, mock_flow_session_deps, monkeypatch
    ):
        """Workers borrowing an owner's execution must not take over its lifecycle."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        fake_repo = FakeExecutionRepository(claimed_execution_id="20240101-777")
        monkeypatch.setattr("qdash.repository.MongoExecutionRepository", lambda: fake_repo)
        lock_repo = MockExecutionLockRepository(locked=True, owner="parent-execution")
        monkeypatch.setattr("qdash.repository.MongoExecutionLockRepository", lambda: lock_repo)
        session = _worker(["0"], execution_id="parent-execution")
        execution_service = MagicMock()
        session.execution_service = execution_service

        session.finish_calibration(update_chip_history=False, push_to_github=False)
        backend = session.backend
        assert backend is not None
        cast("MagicMock", backend.disconnect).assert_called_once_with()
        session.fail_calibration()
        session.cancel_calibration()
        with pytest.raises(RuntimeError, match="cannot own"), session.owned_execution(["0"]):
            pass

        assert fake_repo.calls == []
        assert session.execution_id == "parent-execution"
        assert lock_repo.try_lock_calls == []
        assert lock_repo.owner == "parent-execution"
        assert lock_repo.locked is True
        execution_service.reload.assert_not_called()

    @pytest.mark.parametrize("github", [{"enabled": False}, {"enabled": True}])
    def test_deployment_github_flag_gates_sync_despite_credentials(
        self, mock_flow_session_deps, mock_lock_repo, monkeypatch, github
    ):
        """Credentials alone do not enable sync; ``github.enabled`` gates pull and push."""
        integration = MagicMock()
        monkeypatch.setattr(
            "qdash.common.config.loader.ConfigLoader.load_workflow", lambda: {"github": github}
        )
        monkeypatch.setattr(
            "qdash.workflow.service._internal.session.GitHubIntegration.check_credentials",
            staticmethod(lambda: True),
        )
        monkeypatch.setattr(
            CalibSession,
            "_sync_backend_params_before_push",
            lambda self, logger: self.github_push_config,
        )

        session = _session(
            execution_id="20240101-001",
            qids=["0"],
            lock_repo=mock_lock_repo,
            github=GitHubPolicy.from_deployment("qubex"),
        )
        session.execution_service = cast("Any", MockExecutionService())
        session.github_integration = integration
        integration.push_files.return_value = {"calib_note": "abc"}

        pushed = session._push_to_github_if_configured(MagicMock(), None)

        assert session._orchestrator is not None
        assert session._orchestrator.config.enable_github_pull is github["enabled"]
        assert integration.push_files.called is github["enabled"]
        assert (pushed is None) is not github["enabled"]

    def test_borrowed_session_only_releases_its_backend(self, mock_flow_session_deps):
        settings = _settings(github=GitHubPolicy.pull_and_push())
        spec = WorkerSpec(
            settings=settings.for_worker(),
            lease=WorkerLease(execution_id="parent-execution"),
            mux_mapping=LEGACY_MAPPING,
        )

        with borrowed_session(spec, ["0"]) as session:
            execution_service = MagicMock()
            session.execution_service = execution_service
            backend = session.backend
            assert session._orchestrator is not None
            assert session._orchestrator.config.enable_github_pull is False
            assert session.github_push_config.enabled is False
            assert session._orchestrator.config.skip_execution is True

        assert backend is not None
        cast("MagicMock", backend.disconnect).assert_called_once_with()
        execution_service.reload.assert_not_called()
        assert session._initialized is False

    def test_initialize_takes_a_free_lock_itself(self, mock_flow_session_deps, monkeypatch):
        """Runs that never went through the API, such as cron schedules, lock here."""
        _stub_prefect_flow_run_context(monkeypatch, flow_run_id="flow-run-9")
        monkeypatch.setattr(
            "qdash.repository.MongoExecutionRepository",
            lambda: FakeExecutionRepository(claimed_execution_id="20240101-777"),
        )
        lock_repo = MockExecutionLockRepository()

        session = _session(qids=["0"], lock_repo=lock_repo)

        assert lock_repo.try_lock_calls == ["20240101-777"]
        assert lock_repo.locked is True
        assert lock_repo.owner == session.execution_id


class TestCalibSessionParameterManagement:
    """Test parameter get/set operations."""

    def test_set_and_get_parameter(self, mock_flow_session_deps, mock_lock_repo, mock_user_repo):
        """Test setting and getting parameters."""
        session = _session(
            execution_id="20240101-001",
            qids=["0"],
            lock_repo=mock_lock_repo,
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
        session = _session(
            execution_id="20240101-001",
            qids=["0"],
            lock_repo=mock_lock_repo,
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

        session = CalibSession(
            _settings(
                github=GitHubPolicy(
                    push=GitHubPushConfig(params_file_names=["t1.yaml", "t2_echo.yaml"])
                )
            )
        )
        session._orchestrator = orchestrator

        monkeypatch.setattr(
            "qdash.workflow.service._internal.session.get_params_updater",
            lambda backend, chip_id: FakeUpdater(),
        )
        logger = MagicMock()

        push_config = session._sync_backend_params_before_push(logger)

        assert push_config.params_file_names == ["t1.yaml"]
        # Pipeline steps share the session config, so it must keep the full allowlist.
        assert session.github_push_config.params_file_names == ["t1.yaml", "t2_echo.yaml"]
        logger.info.assert_called_once()

    def test_sync_backend_params_does_not_narrow_later_pipeline_steps(self, monkeypatch):
        """A step that touches no params must not empty the allowlist for later steps."""
        from qdash.workflow.service.github import GitHubPushConfig

        class FakeUpdater:
            def update(self, qid, params):
                return {"capture_delay.yaml"} if params else set()

        orchestrator = MagicMock()
        orchestrator._execution_service = MockExecutionService()
        orchestrator._backend = MagicMock()

        session = CalibSession(
            _settings(
                github=GitHubPolicy(
                    push=GitHubPushConfig(params_file_names=["capture_delay.yaml", "t1.yaml"])
                )
            )
        )
        session._orchestrator = orchestrator
        monkeypatch.setattr(
            "qdash.workflow.service._internal.session.get_params_updater",
            lambda backend, chip_id: FakeUpdater(),
        )

        # Step 1 (ConfigureAll) updates no params.
        orchestrator._execution_service.calib_data.qubit = {}
        first = session._sync_backend_params_before_push(MagicMock())
        # Step 2 (CorrectCaptureDelay) updates the capture delay.
        orchestrator._execution_service.calib_data.qubit = {"0": {"capture_delay": {"value": 8}}}
        second = session._sync_backend_params_before_push(MagicMock())

        assert first.params_file_names == []
        assert second.params_file_names == ["capture_delay.yaml"]

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

        session = CalibSession(
            _settings(
                github=GitHubPolicy(
                    push=GitHubPushConfig(params_file_names=["t1.yaml", "t2_echo.yaml"])
                )
            )
        )
        session._orchestrator = orchestrator

        monkeypatch.setattr(
            "qdash.workflow.service._internal.session.get_params_updater",
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

        push_config = session._sync_backend_params_before_push(logger)

        assert push_config.params_file_names == ["t1.yaml"]
        # Pipeline steps share the session config, so it must keep the full allowlist.
        assert session.github_push_config.params_file_names == ["t1.yaml", "t2_echo.yaml"]
        logger.info.assert_called_once()

    def test_sync_backend_params_pushes_publish_target_files(self, monkeypatch):
        """A publish-only YAML file (control_frequency_fh.yaml) stays in the push."""
        from qdash.datamodel.task import ParameterModel
        from qdash.workflow.engine.task.state_manager import TaskStateManager
        from qdash.workflow.service.github import GitHubPushConfig

        state_manager = TaskStateManager(qids=["0"])
        state_manager.put_output_parameters(
            "CheckAdaptiveFHChevron",
            {"fh_frequency": ParameterModel(value=4.2, unit="GHz")},
            "qubit",
            "0",
            publish_targets={"fh_frequency": ("fh_frequency", "control_frequency_fh")},
        )

        class FakeUpdater:
            def update(self, qid, params):
                assert set(params) == {"fh_frequency", "control_frequency_fh"}
                return set()

        orchestrator = MagicMock()
        orchestrator._execution_service = MockExecutionService()
        orchestrator._execution_service.calib_data = state_manager.calib_data
        orchestrator._backend = MagicMock()

        session = CalibSession(
            _settings(
                github=GitHubPolicy(
                    push=GitHubPushConfig(
                        params_file_names=["control_frequency_fh.yaml", "t1.yaml"]
                    )
                )
            )
        )
        session._orchestrator = orchestrator
        monkeypatch.setattr(
            "qdash.workflow.service._internal.session.get_params_updater",
            lambda backend, chip_id: FakeUpdater(),
        )
        monkeypatch.setattr(
            "qdash.workflow.engine.params_updater.ConfigLoader.load_workflow",
            lambda: {
                "params_updater": {
                    "parameter_file_map": {
                        "control_frequency_fh": "control_frequency_fh.yaml",
                        "t1": "t1.yaml",
                    },
                },
            },
        )

        push_config = session._sync_backend_params_before_push(MagicMock())

        assert push_config.params_file_names == ["control_frequency_fh.yaml"]

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
                        output_parameters={
                            "control_amplitude": {
                                "value": 0.25,
                                "database_updated": True,
                            },
                            "fh_frequency": {
                                "value": 4.25,
                                "database_updated": True,
                                "database_updates": [
                                    {
                                        "parameter_name": "fh_frequency",
                                        "updated_value": 4.25,
                                        "updated": True,
                                    },
                                    {
                                        "parameter_name": "control_frequency_fh",
                                        "updated_value": 4.2,
                                        "updated": True,
                                    },
                                    {
                                        "parameter_name": "not_written",
                                        "updated_value": 4.25,
                                        "updated": False,
                                    },
                                ],
                            },
                            "not_written_only": {
                                "value": 1.0,
                                "database_updated": True,
                                "database_updates": [
                                    {
                                        "parameter_name": "not_written_only",
                                        "updated_value": 1.0,
                                        "updated": False,
                                    }
                                ],
                            },
                            "measurement_only": {
                                "value": 0.75,
                                "database_updated": False,
                            },
                        },
                    )
                ]

        monkeypatch.setattr(
            "qdash.dbmodel.task_result_history.TaskResultHistoryDocument.find",
            lambda query: FakeFinder(),
        )

        orchestrator = MagicMock()
        orchestrator._execution_service = MockExecutionService()

        session = CalibSession(_settings())
        session.execution_id = "exec-1"
        session._orchestrator = orchestrator

        session._merge_task_result_calib_data_before_push(MagicMock())

        execution_service = session.execution_service
        assert execution_service is not None
        merged = execution_service.calib_data.qubit["0"]["control_amplitude"]
        assert isinstance(merged, ParameterModel)
        assert merged.value == 0.25
        # Published destinations are keyed by their database names so the YAML
        # push sees control_frequency_fh.yaml even though the output is fh_frequency.
        qubit_data = execution_service.calib_data.qubit["0"]
        assert qubit_data["fh_frequency"].value == 4.25
        assert qubit_data["control_frequency_fh"].value == 4.2
        assert qubit_data["control_frequency_fh"].parameter_name == "control_frequency_fh"
        assert "not_written" not in qubit_data
        assert "not_written_only" not in qubit_data
        assert "measurement_only" not in qubit_data

    def test_merge_task_result_calib_data_drops_replaced_publish_targets(self, monkeypatch):
        """History reconstruction keeps the latest owner of each published name."""
        from qdash.datamodel.task import ParameterModel, TaskTypes

        def result(task_name: str, target: str, value: float):
            return SimpleNamespace(
                name=task_name,
                qid="0",
                task_type=TaskTypes.QUBIT,
                task_id=f"{task_name}-{target}",
                output_parameters={
                    "measured": {
                        "value": value,
                        "database_updated": True,
                        "database_updates": [
                            {"parameter_name": target, "updated_value": value, "updated": True}
                        ],
                    }
                },
            )

        class FakeFinder:
            def sort(self, sort):
                return self

            def run(self):
                return [
                    SimpleNamespace(
                        name="TaskA",
                        qid="0",
                        task_type=TaskTypes.QUBIT,
                        task_id="TaskA-first",
                        output_parameters={
                            "measured": {
                                "value": 4.2,
                                "database_updated": True,
                                "database_updates": [
                                    {
                                        "parameter_name": "old_alias",
                                        "updated_value": 4.2,
                                        "updated": True,
                                    },
                                    {
                                        "parameter_name": "shared_alias",
                                        "updated_value": 4.2,
                                        "updated": True,
                                    },
                                ],
                            }
                        },
                    ),
                    result("TaskB", "shared_alias", 5.0),
                    result("TaskA", "new_alias", 4.3),
                ]

        monkeypatch.setattr(
            "qdash.dbmodel.task_result_history.TaskResultHistoryDocument.find",
            lambda query: FakeFinder(),
        )
        execution_service = MockExecutionService()
        execution_service.calib_data.qubit["0"] = {
            "old_alias": ParameterModel(value=4.2),
            "shared_alias": ParameterModel(value=5.0),
        }
        session = CalibSession(_settings())
        session.execution_id = "exec-1"
        orchestrator = MagicMock()
        orchestrator._execution_service = execution_service
        session._orchestrator = orchestrator

        session._merge_task_result_calib_data_before_push(MagicMock())

        calib = execution_service.calib_data.qubit["0"]
        assert set(calib) == {"shared_alias", "new_alias"}
        assert calib["shared_alias"].value == 5.0
        assert calib["new_alias"].value == 4.3


class TestOwnedExecution:
    """The one lifecycle every owned Execution goes through."""

    def test_get_session_without_a_running_pipeline(self):
        with pytest.raises(RuntimeError, match="No active calibration session"):
            get_session()

    def test_success_completes_and_releases_without_a_finish_call(
        self, mock_flow_session_deps, mock_lock_repo
    ):
        session = _session(execution_id="20240101-001", lock_repo=mock_lock_repo)

        with session.owned_execution(["0"]) as owned:
            assert owned is session
            assert mock_lock_repo.locked is True

        assert session.execution_service is not None
        assert session.execution_service.completed is True  # type: ignore[attr-defined]
        assert mock_lock_repo.locked is False
        backend = session.backend
        assert backend is not None
        cast("MagicMock", backend.disconnect).assert_called_once_with()

    @pytest.mark.parametrize(
        ("exc", "handler"),
        [
            (RuntimeError("boom"), "fail_calibration"),
            (CancelledRun("cancelled"), "cancel_calibration"),
            (TerminationSignal("SIGTERM"), "abandon_calibration"),
        ],
    )
    def test_abort_routes_to_one_handler(
        self, mock_flow_session_deps, mock_lock_repo, monkeypatch, exc, handler
    ):
        session = _session(execution_id="20240101-001", lock_repo=mock_lock_repo)
        handlers = {
            name: MagicMock()
            for name in ("fail_calibration", "cancel_calibration", "abandon_calibration")
        }
        for name, mock in handlers.items():
            monkeypatch.setattr(session, name, mock)

        with pytest.raises(type(exc)), session.owned_execution(["0"]):
            raise exc

        for name, mock in handlers.items():
            assert mock.called is (name == handler)

    def test_abort_is_kept_when_cleanup_fails(
        self, mock_flow_session_deps, mock_lock_repo, monkeypatch
    ):
        session = _session(execution_id="20240101-001", lock_repo=mock_lock_repo)
        monkeypatch.setattr(
            session, "fail_calibration", MagicMock(side_effect=RuntimeError("cleanup"))
        )

        with pytest.raises(ValueError, match="measurement"), session.owned_execution(["0"]):
            raise ValueError("measurement")


class TestRunPipelineFailureLogging:
    """Test that run_pipeline logs the abort reason and re-raises on step failure."""

    def test_run_pipeline_logs_and_reraises_on_step_failure(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo
    ):
        """A step raising during execute() propagates after the abort is logged."""
        session = _session(execution_id="20240101-001", lock_repo=mock_lock_repo)

        with pytest.raises(RuntimeError, match="boom"):
            session.run_pipeline(QubitTargets(["0"]), [BoomStep()])


@pytest.fixture
def pipeline_execution_env(mock_flow_session_deps, monkeypatch):
    """Exercise real pipeline/strategy lifecycle without hardware or database I/O."""
    records = []
    lock = MockExecutionLockRepository(locked=True, owner="exec-reserved")
    claims = MagicMock(side_effect=["exec-reserved", None])
    monkeypatch.setattr(
        "qdash.workflow.service._internal.session.read_flow_run_id_from_context",
        lambda: "flow-1",
    )
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

                def close(*args, status=status):
                    assert lock.locked  # No stage may release the pipeline lock.
                    record.status = status
                    return self._execution_service

                setattr(self._execution_service, method, close)

    monkeypatch.setattr(
        "qdash.workflow.service._internal.session.CalibOrchestrator", RecordingOrchestrator
    )
    for method in (
        "record_stage_result",
        "_finalize_stale_running_tasks",
        "_finalize_tasks_on_cancel",
        "_update_chip_history",
        "_push_to_github_if_configured",
    ):
        monkeypatch.setattr(CalibSession, method, MagicMock())
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


@pytest.mark.parametrize(
    "mode", ["synchronized", "scheduled", "serial", "simultaneous_spectroscopy"]
)
def test_pipeline_owns_one_execution_per_calibration_step(
    pipeline_execution_env, monkeypatch, mode
):
    from qdash.workflow.service.steps import FilterByStatus, OneQubitCheck, OneQubitFineTune

    env = pipeline_execution_env
    worker_ids = []

    def run_workers(*, plan, qids=None, mux_groups=None, worker=None):
        session = get_session()
        assert env.lock.owner == "exec-reserved"
        assert all(record.status == "completed" for record in env.records[:-1])
        assert plan.step_id in {"one_qubit_check", "one_qubit_fine_tune"}
        worker_ids.append(worker.lease.execution_id if worker else session.execution_id)
        return {"0": {"status": "success"}, "1": {"status": "success"}}

    for method in (
        "run_qubit_calibrations_parallel",
        "run_mux_calibrations_parallel",
        "_calibrate_mux_qubits",
    ):
        monkeypatch.setattr(f"qdash.workflow.service.strategy.{method}", run_workers)

    def run_batch(self, name, qids, **kwargs):
        invocation = kwargs["invocation"]
        run_workers(plan=SimpleNamespace(step_id=invocation.step_id))
        return {qid: {"status": "success", "task_id": f"{name}-{qid}"} for qid in qids}

    monkeypatch.setattr(CalibSession, "execute_task_batch", run_batch)
    # The batch path runs only tasks that implement batch_run.
    check_task, fine_task = (
        ("CheckQubitSpectroscopy", "CheckResonatorSpectroscopy")
        if mode == "simultaneous_spectroscopy"
        else ("CheckRabi", "CheckRamsey")
    )
    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        flow_name="one",
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
    )

    session.run_pipeline(
        QubitTargets(["0", "1"]),
        steps=[
            OneQubitCheck(mode=mode, tasks=[TaskCall(name=check_task)]),
            FilterByStatus(),
            OneQubitFineTune(mode=mode, tasks=[TaskCall(name=fine_task)]),
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
        def execute(self, session, targets, ctx):
            return ctx

    class FailureStep(BoomStep):
        def execute(self, session, targets, ctx):
            assert env.lock.locked
            assert env.records[0].status == "completed"
            raise CancelledRun() if cancel else RuntimeError("boom")

    class FailureTransform(FailureStep, TransformStep):
        pass

    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
    )
    with pytest.raises(CancelledRun if cancel else RuntimeError):
        session.run_pipeline(
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


def test_single_step_without_api_reservation_creates_one_execution(
    pipeline_execution_env, monkeypatch
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
    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
    )
    session.run_pipeline(
        QubitTargets(["0"]), steps=[CustomOneQubit(tasks=[TaskCall(name="CheckRabi")])]
    )

    assert len(env.records) == 1
    assert env.records[0].status == "completed"
    assert env.records[0].config.skip_execution is False
    assert (
        worker.call_args.kwargs["worker"].lease.execution_id == env.records[0].config.execution_id
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
    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        backend_name="fake",
        lock_repo=env.lock,
        counter_repo=FakeExecutionCounterRepository(2),
        default_run_parameters={"interval": {"value": 1024, "value_type": "int"}},
        task_defaults={"CheckRabi": {"run": {"shots": {"value": 2048, "value_type": "int"}}}},
    )
    session.run_pipeline(
        QubitTargets(["0", "1"]),
        steps=[
            CustomTwoQubit(tasks=[TaskCall(name="CheckCrossResonance")]),
            TwoQubitCalibration(),
        ],
    )
    assert len(env.records) == 2
    specs = [call.kwargs["worker"] for call in worker.call_args_list]
    assert [spec.lease.execution_id for spec in specs] == [
        record.config.execution_id for record in env.records
    ]
    assert all(spec.settings.backend_name == "fake" for spec in specs)
    assert all(
        spec.settings.default_run_parameters == session.default_run_parameters for spec in specs
    )
    assert all(spec.settings.task_defaults == session.task_parameters for spec in specs)
    assert all(spec.settings.github == GitHubPolicy.disabled() for spec in specs)
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


def test_coupling_override_plans_only_the_selected_pairs(pipeline_wiring):
    """A source schedule replaced by a pair override no longer reserves its qubits."""
    from qdash.datamodel.flow_targets import FlowTargetOverride
    from qdash.workflow.service.flow_targets import override_pipeline
    from qdash.workflow.service.pipeline_resources import plan_pipeline_resources
    from qdash.workflow.service.steps import SetCRSchedule, TwoQubitCalibration
    from qdash.workflow.service.targets import CouplingTargets

    targets, steps = override_pipeline(
        CouplingTargets([("8", "12")]),
        [SetCRSchedule(schedule=[[("8", "12")]]), TwoQubitCalibration()],
        FlowTargetOverride(coupling_pairs=[["1", "0"]]),
        lambda pairs: [pairs],
    )
    scope = plan_pipeline_resources("chip-1", targets, steps)
    assert not scope.exclusive
    assert {r for r in scope.resources if r.startswith("mux:")} == {"mux:0"}


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
    session = _session(username="alice", chip_id="chip-1", project_id="project-1", lock_repo=repo)
    with pytest.raises(RuntimeError, match="already running"):
        session.run_pipeline(QubitTargets(["0"]), [CustomOneQubit(), ConfigureAll(mux_ids=[1])])
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

    def first(self, session, targets, ctx):
        seen.append(session.execution_id)
        assert not repo.try_lock("project-1", "intruder", "chip-1", ("mux:1",), False)
        return ctx

    def second(self, session, targets, ctx):
        seen.append(session.execution_id)
        assert not repo.try_lock("project-1", "intruder", "chip-1", ("mux:0",), False)
        assert not repo.try_lock("project-1", "intruder", "chip-1", ("mux:1",), False)
        if fail:
            raise RuntimeError("second step failed")
        return ctx

    monkeypatch.setattr(CustomOneQubit, "execute", first)
    monkeypatch.setattr(ConfigureAll, "execute", second)
    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        lock_repo=repo,
        counter_repo=FakeExecutionCounterRepository(2),
    )
    if fail:
        with pytest.raises(RuntimeError, match="second step failed"):
            session.run_pipeline(QubitTargets(["0"]), [CustomOneQubit(), ConfigureAll(mux_ids=[1])])
    else:
        session.run_pipeline(QubitTargets(["0"]), [CustomOneQubit(), ConfigureAll(mux_ids=[1])])
    assert seen[0] == "exec-reserved"
    assert seen[1] != seen[0]
    assert [record.config.connect_backend for record in pipeline_execution_env.records] == [
        False,
        True,
    ]
    assert repo.try_lock("project-1", "next-run", "chip-1", (), True)
    assert not repo.try_lock("project-1", "other", "chip-2", ("mux:0",), False)


def test_pipeline_rejects_unplanned_targets_before_later_hardware_step(
    pipeline_execution_env,
    pipeline_wiring,
    monkeypatch,
):
    from qdash.workflow.service.steps import CustomOneQubit, SetCRSchedule

    def change_targets(self, session, targets, ctx):
        ctx.candidate_qids = ["12"]  # The declared schedule only reserved MUX 0.
        return ctx

    run_step = MagicMock()
    monkeypatch.setattr(SetCRSchedule, "execute", change_targets)
    monkeypatch.setattr(CustomOneQubit, "execute", run_step)
    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        lock_repo=pipeline_execution_env.lock,
    )
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.run_pipeline(
            QubitTargets(["0"]), [SetCRSchedule(schedule=[[("0", "1")]]), CustomOneQubit()]
        )
    run_step.assert_not_called()
    assert not pipeline_execution_env.lock.locked


def _borrowing_worker(scope: Any, **overrides: Any) -> CalibSession:
    """A worker session of the reservation ``scope`` that has not opened a backend."""
    return CalibSession(
        _settings(username="alice", chip_id="chip-1", project_id="project-1", **overrides),
        lease=WorkerLease(execution_id="child", reservation=ReservationScope.of(scope)),
        mux_mapping=MuxMapping.legacy(),
    )


def test_task_and_isolated_worker_reject_unreserved_hardware(
    pipeline_wiring, mock_flow_session_deps
):
    from qdash.common.execution_resources import resolve_execution_resource_scope

    scope = resolve_execution_resource_scope("chip-1", {"qid": "0"})
    session = _borrowing_worker(scope)
    orchestrator = MagicMock()
    session._orchestrator = orchestrator
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.execute_task("CheckRabi", "4")
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.execute_task_batch("CheckRabi", ["0", "4"])
    with pytest.raises(RuntimeError, match="outside the workflow"):
        session.execute_task("ConfigureAll", "", parameters={"run": {"mux_ids": {"value": [1]}}})
    orchestrator.run_task.assert_not_called()
    orchestrator.run_task_batch.assert_not_called()
    spec = WorkerSpec(
        settings=_settings(username="alice", chip_id="chip-1", project_id="project-1"),
        lease=WorkerLease(execution_id="child", reservation=ReservationScope.of(scope)),
        mux_mapping=LEGACY_MAPPING,
    )
    with pytest.raises(RuntimeError, match="outside the workflow"), borrowed_session(spec, ["4"]):
        pass


def test_configure_all_scope_uses_session_task_defaults(pipeline_wiring):
    """Per-task MUX defaults are used for operation scope validation."""
    from qdash.common.execution_resources import resolve_execution_resource_scope

    scope = resolve_execution_resource_scope("chip-1", {"mux_ids": [0]})
    session = _borrowing_worker(scope, task_defaults={"ConfigureAll": {"run": {"mux_ids": [0]}}})
    orchestrator = MagicMock()
    session._orchestrator = orchestrator

    session.execute_task("ConfigureAll", "")

    orchestrator.run_task.assert_called_once()


def test_pipeline_keeps_supplied_reservation_owner(pipeline_execution_env, monkeypatch):
    from qdash.workflow.service.steps import CustomOneQubit

    monkeypatch.setattr(CustomOneQubit, "execute", lambda self, session, targets, ctx: ctx)
    session = _session(
        username="alice",
        chip_id="chip-1",
        project_id="project-1",
        execution_id="exec-reserved",
        lock_repo=pipeline_execution_env.lock,
    )
    session.run_pipeline(QubitTargets(["0"]), [CustomOneQubit()])
    assert pipeline_execution_env.lock.try_lock_calls == ["exec-reserved"]
    assert pipeline_execution_env.lock.unlock_calls == ["exec-reserved"]
    with pytest.raises(RuntimeError, match="No hardware reservation"):
        session.execute_task("CheckRabi", "0")


class TestAbortClassification:
    """Test _is_cancellation and _is_external_termination exception matching."""

    def test_bare_cancelled_run_is_a_cancellation(self):
        """A bare CancelledRun is a cancellation and not an external termination."""
        exc = CancelledRun("cancelled")
        assert _is_cancellation(exc) is True
        assert _is_external_termination(exc) is False

    def test_bare_termination_signal_is_an_external_termination(self):
        """A bare TerminationSignal is an external termination and not a cancellation."""
        exc = TerminationSignal("SIGTERM")
        assert _is_external_termination(exc) is True
        assert _is_cancellation(exc) is False

    def test_unrelated_exception_is_neither(self):
        """A plain RuntimeError is neither a cancellation nor an external termination."""
        exc = RuntimeError("boom")
        assert _is_cancellation(exc) is False
        assert _is_external_termination(exc) is False

    def test_cancelled_run_as_cause_is_recognised(self):
        """A CancelledRun attached as __cause__ of a RuntimeError is still a cancellation."""
        try:
            try:
                raise CancelledRun("cancelled")
            except CancelledRun as cause:
                raise RuntimeError("wrapped") from cause
        except RuntimeError as exc:
            assert _is_cancellation(exc) is True

    def test_cancelled_run_nested_in_exception_group_is_recognised(self):
        """A CancelledRun nested in an ExceptionGroup alongside a ValueError is still recognised."""
        group = ExceptionGroup(  # noqa: F821 (3.11 builtin; ruff targets py310)
            "multiple errors", [CancelledRun("cancelled"), ValueError("other")]
        )
        assert _is_cancellation(group) is True

    def test_termination_signal_as_cause_is_recognised(self):
        """A TerminationSignal attached as __cause__ is an external termination.

        This matches Prefect's async path, which raises
        ``TerminationSignal(...) from exc``.
        """
        try:
            try:
                raise RuntimeError("original")
            except RuntimeError as cause:
                raise TerminationSignal("SIGTERM") from cause
        except TerminationSignal as exc:
            assert _is_external_termination(exc) is True

    def test_context_is_not_followed(self):
        """__context__ is not followed: a real failure while handling a cancellation is not mistaken for one."""
        try:
            try:
                raise CancelledRun("cancelled")
            except CancelledRun:
                raise RuntimeError("real failure") from None
        except RuntimeError as exc:
            assert exc.__context__ is not None
            assert _is_cancellation(exc) is False

    def test_self_referencing_cause_does_not_hang(self):
        """A self-referencing __cause__ does not hang the exception chain walk."""
        exc = RuntimeError("boom")
        exc.__cause__ = exc
        assert _is_cancellation(exc) is False
        assert _is_external_termination(exc) is False


def _build_abort_handling_session(mock_lock_repo, mock_user_repo) -> CalibSession:
    """Build a CalibSession the same way TestRunPipelineFailureLogging does."""
    return _session(
        execution_id="20240101-001",
        qids=["0"],
        lock_repo=mock_lock_repo,
    )


def _mock_terminal_handlers(
    session: CalibSession, monkeypatch: pytest.MonkeyPatch
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Replace the three terminal handlers so the abort branch can be observed."""
    fail, cancel, abandon = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(session, "fail_calibration", fail)
    monkeypatch.setattr(session, "cancel_calibration", cancel)
    monkeypatch.setattr(session, "abandon_calibration", abandon)
    return fail, cancel, abandon


class TestRunPipelineAbortHandling:
    """Test that _run_pipeline routes aborts to the correct terminal handler."""

    def test_unrelated_exception_calls_fail_calibration(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo, monkeypatch
    ):
        """A plain RuntimeError routes to fail_calibration only."""
        session = _build_abort_handling_session(mock_lock_repo, mock_user_repo)
        fail, cancel, abandon = _mock_terminal_handlers(session, monkeypatch)
        exc = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            session.run_pipeline(QubitTargets(["0"]), [RaisingStep(exc=exc)])

        fail.assert_called_once()
        cancel.assert_not_called()
        abandon.assert_not_called()

    def test_cancelled_run_calls_cancel_calibration(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo, monkeypatch
    ):
        """A CancelledRun routes to cancel_calibration only."""
        session = _build_abort_handling_session(mock_lock_repo, mock_user_repo)
        fail, cancel, abandon = _mock_terminal_handlers(session, monkeypatch)
        exc = CancelledRun("cancelled")

        with pytest.raises(CancelledRun):
            session.run_pipeline(QubitTargets(["0"]), [RaisingStep(exc=exc)])

        cancel.assert_called_once()
        fail.assert_not_called()
        abandon.assert_not_called()

    def test_termination_signal_calls_abandon_calibration(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo, monkeypatch
    ):
        """A TerminationSignal routes to abandon_calibration only."""
        session = _build_abort_handling_session(mock_lock_repo, mock_user_repo)
        fail, cancel, abandon = _mock_terminal_handlers(session, monkeypatch)
        exc = TerminationSignal("SIGTERM")

        with pytest.raises(TerminationSignal):
            session.run_pipeline(QubitTargets(["0"]), [RaisingStep(exc=exc)])

        abandon.assert_called_once()
        fail.assert_not_called()
        cancel.assert_not_called()

    def test_abandon_calibration_releases_lock_without_closing_execution(
        self, mock_flow_session_deps, mock_lock_repo, mock_user_repo
    ):
        """abandon_calibration releases the lock and resets state without a terminal write."""
        session = _build_abort_handling_session(mock_lock_repo, mock_user_repo)
        session._lock_acquired = True
        session._lock_repo = mock_lock_repo
        execution_service = MagicMock()
        session.execution_service = execution_service

        session.abandon_calibration()

        assert session._lock_acquired is False
        assert session._initialized is False
        execution_service.complete.assert_not_called()
        execution_service.fail.assert_not_called()
        execution_service.cancel.assert_not_called()


@pytest.mark.parametrize("signal", [TerminationSignal("SIGTERM"), asyncio.CancelledError()])
def test_initialization_interrupt_releases_the_reservation(
    mock_flow_session_deps, monkeypatch, signal
):
    """An interrupted initialization frees its claim before the caller can close anything."""
    lock = MockExecutionLockRepository()

    def interrupt(self):
        """Interrupt initialization after its reservation has been acquired."""
        assert lock.locked
        raise signal

    monkeypatch.setattr(MockCalibOrchestrator, "initialize", interrupt)
    with pytest.raises(type(signal)) as raised:
        _session(
            qids=["0"],
            execution_id="20261022-008",
            lock_repo=lock,
        )
    assert raised.value is signal
    assert not lock.locked
    assert lock.unlock_calls == ["20261022-008"]


# =============================================================================
# One settings record: what parent, step, worker, single-task and rerun share
# =============================================================================


def _rerun_settings(**overrides: Any) -> SessionSettings:
    from qdash.workflow.service._internal.settings import SnapshotSource

    values: dict[str, Any] = {
        "flow_name": "rerun",
        "tags": ["t"],
        "note": {"k": "v"},
        "default_run_parameters": {"interval": 8},
        "task_defaults": {"CheckRabi": {"run": {"shots": 256}}},
        "configuration_mode": "ge-ef-cr",
        "snapshot": SnapshotSource(
            execution_id="exec-src", task_id="task-src", exempt_tasks=frozenset({"Configure"})
        ),
        "force_update_params": True,
        "github": GitHubPolicy.pull_and_push(),
    }
    values.update(overrides)
    return _settings(**values)


def test_worker_spec_inherits_every_measurement_setting(mock_flow_session_deps, mock_lock_repo):
    """Snapshot source, exempt tasks and force updates reach workers; GitHub does not."""
    import pickle

    from qdash.common.execution_resources import resolve_execution_resource_scope

    owner = CalibSession(
        _rerun_settings(), repositories=SessionRepositories(lock_repo=mock_lock_repo)
    )
    owner.execution_id = "exec-step"
    owner._initialize(["0"])

    spec = owner.worker_spec()

    assert spec.settings == owner.settings.model_copy(update={"github": GitHubPolicy.disabled()})
    assert spec.settings.snapshot == owner.settings.snapshot
    assert spec.settings.force_update_params is True
    assert spec.lease.execution_id == "exec-step"
    assert spec.lease.reservation == ReservationScope.of(
        resolve_execution_resource_scope("chip_1", {"qids": ["0"]})
    )
    # Prefect and Dask move the spec to worker processes unchanged.
    assert pickle.loads(pickle.dumps(spec)) == spec  # noqa: S301


def test_workers_apply_the_inherited_snapshot_and_force_override(
    mock_flow_session_deps, monkeypatch
):
    loaders: list[dict[str, Any]] = []

    class RecordingLoader:
        def __init__(self, **kwargs: Any) -> None:
            loaders.append(kwargs)

    monkeypatch.setattr(
        "qdash.workflow.engine.task.snapshot_loader.SnapshotParameterLoader", RecordingLoader
    )
    spec = WorkerSpec(
        settings=_rerun_settings().for_worker(),
        lease=WorkerLease(execution_id="exec-step"),
        mux_mapping=LEGACY_MAPPING,
    )

    with borrowed_session(spec, ["0"]) as worker:
        assert worker._orchestrator is not None
        config = worker._orchestrator.config
        assert config.force_update_params is True
        assert config.configuration_mode == "ge-ef-cr"
        assert config.task_parameters == spec.settings.task_defaults
        assert config.default_run_parameters == spec.settings.default_run_parameters
        assert config.enable_github_pull is False
        assert config.skip_execution is True

    assert loaders == [
        {
            "source_execution_id": "exec-src",
            "project_id": "test_project",
            "source_task_id": "task-src",
            "snapshot_exempt_tasks": {"Configure"},
        }
    ]


def test_without_a_snapshot_no_loader_is_created(mock_flow_session_deps, monkeypatch):
    loader = MagicMock()
    monkeypatch.setattr(
        "qdash.workflow.engine.task.snapshot_loader.SnapshotParameterLoader", loader
    )

    _worker(["0"])

    loader.assert_not_called()


def test_pipeline_steps_share_settings_except_their_metadata(pipeline_execution_env, monkeypatch):
    """Every step session and its workers see the run's settings, step by step."""
    from qdash.workflow.service.steps import CustomOneQubit

    seen: list[tuple[SessionSettings, WorkerSpec]] = []

    def capture(self, session, targets, ctx):
        seen.append((session.settings, session.worker_spec()))
        return ctx

    monkeypatch.setattr(CustomOneQubit, "execute", capture)
    base = _rerun_settings(github=GitHubPolicy.disabled())
    session = CalibSession(
        base,
        repositories=SessionRepositories(
            lock_repo=pipeline_execution_env.lock,
            counter_repo=FakeExecutionCounterRepository(2),
        ),
    )

    session.run_pipeline(
        QubitTargets(["0"]),
        [CustomOneQubit(step_name="first"), CustomOneQubit(step_name="second")],
    )

    assert len(seen) == 2
    for step_settings, spec in seen:
        unchanged = step_settings.model_copy(update={"flow_name": None, "note": None})
        assert unchanged == base.model_copy(update={"flow_name": None, "note": None})
        assert spec.settings == step_settings.for_worker()
    assert [s.flow_name for s, _ in seen] == ["rerun_first", "rerun_second"]
    assert seen[0][1].lease.execution_id != seen[1][1].lease.execution_id
    assert session.settings == base


def test_configure_all_layout_reaches_later_steps_and_their_workers(
    pipeline_execution_env, monkeypatch
):
    from qdash.workflow.service.steps import ConfigureAll, CustomOneQubit

    modes: list[tuple[str | None, str | None]] = []
    monkeypatch.setattr(ConfigureAll, "execute", lambda self, session, targets, ctx: ctx)

    def capture(self, session, targets, ctx):
        assert session._orchestrator is not None
        modes.append(
            (
                session._orchestrator.config.configuration_mode,
                session.worker_spec().settings.configuration_mode,
            )
        )
        return ctx

    monkeypatch.setattr(CustomOneQubit, "execute", capture)
    session = _session(
        lock_repo=pipeline_execution_env.lock, counter_repo=FakeExecutionCounterRepository(2)
    )

    session.run_pipeline(
        QubitTargets(["0"]),
        [
            ConfigureAll(
                mux_ids=[0],
                call=TaskCall(name="ConfigureAll", run={"configuration_mode": "ge-ef-fh"}),
            ),
            CustomOneQubit(),
        ],
    )

    assert modes == [("ge-ef-fh", "ge-ef-fh")]
    configure_record = pipeline_execution_env.records[0]
    assert configure_record.config.configuration_mode == "ge-ef-fh"
    assert session.settings.configuration_mode is None


# =============================================================================
# The public run owns cleanup: no finish call, success, failure or cancellation
# =============================================================================


@pytest.fixture
def public_run_env(pipeline_execution_env, monkeypatch):
    from itertools import count

    ids = count(1)
    monkeypatch.setattr(
        "qdash.repository.MongoExecutionLockRepository", lambda: pipeline_execution_env.lock
    )
    monkeypatch.setattr(
        "qdash.workflow.service._internal.session.generate_execution_id",
        lambda *args, **kwargs: f"exec-generated-{next(ids)}",
    )
    monkeypatch.setattr(
        "qdash.workflow.service._internal.runs.load_flow_default_run_parameters",
        lambda project_id, flow_name: {},
    )
    return pipeline_execution_env


@pytest.mark.parametrize("outcome", ["completed", "failed", "cancelled"])
def test_public_run_closes_every_execution_without_a_finish_call(public_run_env, outcome):
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.steps import CustomOneQubit
    from tests.qdash.workflow.context_helpers import granted_context

    class Last(CustomOneQubit):
        def execute(self, session, targets, ctx):
            if outcome == "failed":
                raise RuntimeError("measurement failed")
            if outcome == "cancelled":
                raise CancelledRun("cancelled")
            return ctx

    class First(CustomOneQubit):
        def execute(self, session, targets, ctx):
            return ctx

    cal = CalibService.from_context(granted_context(project_id="project-1"), flow_name="run")
    steps = [First(step_name="first"), Last(step_name="last")]
    if outcome == "completed":
        cal.run(QubitTargets(["0"]), steps=steps)
    else:
        with pytest.raises((RuntimeError, CancelledRun)):
            cal.run(QubitTargets(["0"]), steps=steps)

    assert [record.status for record in public_run_env.records] == ["completed", outcome]
    assert public_run_env.lock.locked is False
    assert public_run_env.lock.unlock_calls == ["exec-reserved"]
    with pytest.raises(RuntimeError, match="No active"):
        get_session()


def test_public_run_leaves_a_terminated_execution_to_the_flow_hooks(public_run_env, monkeypatch):
    from qdash.workflow.service import CalibService
    from qdash.workflow.service.steps import CustomOneQubit
    from tests.qdash.workflow.context_helpers import granted_context

    def terminated(self, session, targets, ctx):
        raise TerminationSignal("SIGTERM")

    monkeypatch.setattr(CustomOneQubit, "execute", terminated)
    cal = CalibService.from_context(granted_context(project_id="project-1"))

    with pytest.raises(TerminationSignal):
        cal.run(QubitTargets(["0"]), steps=[CustomOneQubit()])

    # Prefect's on_cancellation/on_crashed hooks record the outcome; the run
    # only releases its backend and reservation.
    assert [record.status for record in public_run_env.records] == ["running"]
    assert public_run_env.lock.locked is False
