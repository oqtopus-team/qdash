# Workflow Testing Guidelines

## Overview

The workflow module handles calibration workflow orchestration using Prefect. Tests should verify:

- **Task state management**: TaskManager, TaskStateManager state transitions
- **Execution lifecycle**: ExecutionManager, ExecutionService operations
- **Scheduling logic**: CRScheduler parallel grouping and conflict detection
- **Result processing**: R² validation, fidelity checks, parameter handling
- **Data persistence**: File saving, history recording
- **Flow helpers**: Python Flow Editor API functions
- **Context management**: Session context thread safety

### Test Framework

- **Framework**: pytest
- **Mocking**: unittest.mock (MagicMock, patch)
- **Fixtures**: pytest fixtures with proper scope management
- **Database**: MongoDB via init_db fixture (shared conftest.py)

---

## Test Directory Structure

Tests mirror the source directory structure:

```
tests/qdash/workflow/
├── __init__.py
├── engine/
│   ├── __init__.py
│   └── calibration/
│       ├── __init__.py
│       ├── task/                          # Task management tests
│       │   ├── __init__.py
│       │   ├── test_manager.py            # TaskManager tests
│       │   ├── test_executor.py           # TaskExecutor tests
│       │   ├── test_state_manager.py      # TaskStateManager tests
│       │   ├── test_result_processor.py   # TaskResultProcessor tests
│       │   └── test_history_recorder.py   # TaskHistoryRecorder tests
│       ├── execution/                     # Execution management tests
│       │   ├── __init__.py
│       │   ├── test_manager.py            # ExecutionManager tests
│       │   ├── test_state_manager.py      # ExecutionStateManager tests
│       │   └── test_service.py            # ExecutionService tests
│       ├── scheduler/                     # Scheduler tests
│       │   ├── __init__.py
│       │   ├── test_cr_scheduler.py       # CRScheduler tests
│       │   └── test_plugins.py            # Scheduler plugins tests
│       └── repository/                    # Repository tests
│           ├── __init__.py
│           └── test_filesystem_impl.py    # Filesystem implementation tests
└── service/                           # Calibration service tests
    ├── __init__.py
    ├── test_config.py                 # CalibServiceConfig tests
    ├── test_factory.py                # Factory tests
    ├── test_context.py                # SessionContext tests
    └── test_session.py                # CalibService tests
```

### Mapping Rules

| Source Path                                                       | Test Path                                                                |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `src/qdash/workflow/engine/calibration/task/manager.py`           | `tests/qdash/workflow/engine/calibration/task/test_manager.py`           |
| `src/qdash/workflow/engine/calibration/task/executor.py`          | `tests/qdash/workflow/engine/calibration/task/test_executor.py`          |
| `src/qdash/workflow/engine/calibration/task/state_manager.py`     | `tests/qdash/workflow/engine/calibration/task/test_state_manager.py`     |
| `src/qdash/workflow/engine/calibration/execution/manager.py`      | `tests/qdash/workflow/engine/calibration/execution/test_manager.py`      |
| `src/qdash/workflow/engine/calibration/execution/service.py`      | `tests/qdash/workflow/engine/calibration/execution/test_service.py`      |
| `src/qdash/workflow/engine/calibration/scheduler/cr_scheduler.py` | `tests/qdash/workflow/engine/calibration/scheduler/test_cr_scheduler.py` |
| `src/qdash/workflow/service/context.py`                           | `tests/qdash/workflow/service/test_context.py`                           |
| `src/qdash/workflow/service/session.py`                           | `tests/qdash/workflow/service/test_session.py`                           |

---

## Test File Naming Conventions

### File Naming

- Prefix: `test_`
- Name: Module name being tested
- Extension: `.py`

```python
# Good
test_task_manager.py
test_cr_scheduler.py
test_flow_helpers.py

# Bad
task_manager_tests.py
TestTaskManager.py
```

### Module Docstrings

Each test file should have a module-level docstring explaining the purpose:

```python
"""Tests for TaskManager.

These tests verify the core behavior of TaskManager to serve as a safety net
during refactoring. Tests cover:
1. Task state management (start_task, end_task, update_task_status)
2. Parameter management (put_input_parameters, put_output_parameters)
3. Figure/raw data saving (save_figures, save_raw_data)
"""
```

---

## Test Class and Method Naming

### Class Naming

Group related tests into classes with descriptive names:

```python
# Good - Descriptive class names
class TestTaskStateManagement:
    """Test task state transitions."""

class TestParameterManagement:
    """Test parameter handling."""

class TestFigureAndDataSaving:
    """Test figure and raw data saving."""

class TestBatchOperations:
    """Test batch task operations."""

# Bad
class TestTaskManager:  # Too generic
class Tests:            # Not descriptive
```

### Method Naming

Use snake*case with `test*` prefix. Include the action and expected outcome:

```python
# Good - Clear action and expectation
def test_start_task_updates_status_to_running(self):
def test_ensure_task_exists_is_idempotent(self):
def test_get_task_raises_for_nonexistent_task(self):
def test_execute_task_with_r2_validation_fail(self):

# Bad
def test_start_task(self):           # Missing expectation
def test1(self):                     # Not descriptive
def test_it_works(self):             # Vague
```

---

## Test Organization Pattern

### AAA Pattern (Arrange-Act-Assert)

Always structure tests using the AAA pattern:

```python
def test_start_task_updates_status_to_running(self):
    """Test start_task changes status to RUNNING."""
    # Arrange
    tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
    tm._ensure_task_exists("CheckRabi", "qubit", "0")

    # Act
    tm.start_task("CheckRabi", "qubit", "0")

    # Assert
    task = tm.get_task("CheckRabi", "qubit", "0")
    assert task.status == TaskStatusModel.RUNNING
    assert task.start_at != ""
```

### Single Concept Per Test

Each test should verify one concept:

```python
# Good - Single concept
def test_update_task_status_to_completed(self):
    """Test update_task_status_to_completed."""
    tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
    tm._ensure_task_exists("CheckRabi", "qubit", "0")

    tm.update_task_status_to_completed("CheckRabi", "Task done", "qubit", "0")

    task = tm.get_task("CheckRabi", "qubit", "0")
    assert task.status == TaskStatusModel.COMPLETED
    assert task.message == "Task done"

def test_update_task_status_to_failed(self):
    """Test update_task_status_to_failed."""
    tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
    tm._ensure_task_exists("CheckRabi", "qubit", "0")

    tm.update_task_status_to_failed("CheckRabi", "Error occurred", "qubit", "0")

    task = tm.get_task("CheckRabi", "qubit", "0")
    assert task.status == TaskStatusModel.FAILED
    assert task.message == "Error occurred"
```

---

## Fixture Patterns

### Basic Fixtures

Define fixtures for commonly used objects:

```python
@pytest.fixture
def mock_task(self):
    """Create a mock task for testing."""
    task = MagicMock()
    task.get_name.return_value = "CheckRabi"
    task.get_task_type.return_value = "qubit"
    task.is_qubit_task.return_value = True
    task.is_coupling_task.return_value = False
    task.backend = "fake"
    task.r2_threshold = 0.7
    task.name = "CheckRabi"
    return task

@pytest.fixture
def mock_session(self):
    """Create a mock session for testing."""
    session = MagicMock()
    session.name = "fake"
    return session

@pytest.fixture
def mock_execution_manager(self):
    """Create a mock execution manager for testing."""
    em = MagicMock()
    em.execution_id = "test-exec-001"
    em.chip_id = "test-chip"
    em.to_datamodel.return_value = ExecutionModel(...)
    em.update_with_task_manager.return_value = em
    return em
```

### Temporary Directory Fixtures

Use pytest's `tmp_path` or `tempfile` for file operations:

```python
@pytest.fixture
def calib_dir(self):
    """Create a temporary calibration directory with required subdirectories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "task").mkdir()
        Path(tmpdir, "fig").mkdir()
        Path(tmpdir, "raw_data").mkdir()
        yield tmpdir

def test_save_figures_creates_files(self):
    """Test save_figures creates png and json files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir=tmpdir)
        # ... test code
```

### Mock Class Fixtures

Create mock implementations for complex dependencies:

```python
class MockTask:
    """Mock task for testing."""

    def __init__(
        self,
        name: str = "CheckRabi",
        task_type: str = "qubit",
        r2_threshold: float = 0.7,
        backend: str = "fake",
    ):
        self.name = name
        self._task_type = task_type
        self.r2_threshold = r2_threshold
        self.backend = backend

    def get_name(self) -> str:
        return self.name

    def get_task_type(self) -> str:
        return self._task_type

    def preprocess(self, session, qid):
        return PreProcessResult(input_parameters={"param1": ParameterModel(value=1.0)})

    def run(self, session, qid):
        return RunResult(raw_result={"data": [1, 2, 3]}, r2={"0": 0.95})

    def postprocess(self, session, execution_id, run_result, qid):
        return PostProcessResult(
            output_parameters={"qubit_frequency": ParameterModel(value=5.0)},
            figures=[],
            raw_data=[],
        )
```

### Setup/Teardown Methods

Use `setup_method` for per-test initialization:

```python
class TestSessionContext:
    """Test SessionContext class."""

    def setup_method(self):
        """Clear session before each test."""
        clear_current_session()

    def test_set_and_get_session(self):
        """Test setting and getting session."""
        context = SessionContext()
        mock_session = MagicMock()
        context.set_session(mock_session)
        result = context.get_session()
        assert result is mock_session
```

---

## Mocking Patterns

### Patching Database Dependencies

Use `patch` for database operations:

```python
def test_execute_task_without_run_result(
    self, init_db, mock_task, mock_session, mock_execution_manager, calib_dir
):
    """Test execute_task when run returns None."""
    tm = TaskManager(
        username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
    )

    mock_task.preprocess.return_value = None
    mock_task.run.return_value = None

    with (
        patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
        patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
    ):
        mock_chip_doc.get_current_chip.return_value = MagicMock()

        em_result, tm_result = tm.execute_task(
            task_instance=mock_task,
            session=mock_session,
            execution_manager=mock_execution_manager,
            qid="0",
        )

    task = tm_result.get_task("CheckRabi", "qubit", "0")
    assert task.status == TaskStatusModel.COMPLETED
```

### Monkeypatching for Module-Level State

Use `monkeypatch` for global state:

```python
def test_flow_session_attributes(self, monkeypatch):
    """Test that FlowSession initializes with correct attributes."""

    class MockExecutionManager:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
            self.calib_data_path = kwargs.get("calib_data_path", "")
            self.calib_data = type("obj", (object,), {"qubit": {}, "coupling": {}})()

        def save(self):
            return self

    monkeypatch.setattr(
        "qdash.workflow.helpers.flow_helpers.ExecutionManager",
        MockExecutionManager,
    )
```

### Mocking Method Return Values

Configure mock return values and side effects:

```python
@pytest.fixture
def mock_result_processor(self):
    """Create a mock result processor."""
    processor = MagicMock()
    processor.validate_r2.return_value = True
    processor.process_output_parameters.return_value = {
        "qubit_frequency": ParameterModel(
            value=5.0, execution_id="exec-001", task_id="task-001"
        )
    }
    return processor

def test_execute_task_raises_on_r2_validation_failure(
    self, executor, mock_result_processor, mock_state_manager
):
    """Test execute_task raises on R² validation failure."""
    mock_result_processor.validate_r2.side_effect = R2ValidationError("R² value too low")
    task = MockTask()
    session = MockSession()

    with pytest.raises(ValueError, match="R² value too low"):
        executor.execute_task(task, session, "0")
```

### Patching Class Methods

Use `patch.object` for class method patching:

```python
@patch.object(CRScheduler, "_load_chip_data")
def test_generate_with_design_based_direction(mock_load, scheduler):
    """Test schedule generation using design-based direction inference."""
    chip_doc = MagicMock()
    chip_doc.qubits = {...}
    mock_load.return_value = chip_doc

    schedule = scheduler.generate(candidate_qubits=["0", "1", "2", "3"])

    assert schedule.metadata["direction_method"] == "design_based"
```

---

## Testing Calibration Engine Components

### TaskManager Tests

Test task lifecycle and state management:

```python
class TestTaskStateManagement:
    """Test task state transitions."""

    def test_init_creates_empty_task_containers_for_qids(self):
        """Test TaskManager initialization with qids."""
        qids = ["0", "1", "2"]
        tm = TaskManager(username="test", execution_id="test-001", qids=qids, calib_dir="/tmp")

        for qid in qids:
            assert qid in tm.task_result.qubit_tasks
            assert qid in tm.task_result.coupling_tasks
            assert qid in tm.calib_data.qubit
            assert tm.task_result.qubit_tasks[qid] == []

    def test_ensure_task_exists_adds_new_task(self):
        """Test _ensure_task_exists adds task to container."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tasks = tm.task_result.qubit_tasks["0"]
        assert len(tasks) == 1
        assert tasks[0].name == "CheckRabi"
        assert tasks[0].status == TaskStatusModel.SCHEDULED
```

### TaskExecutor Tests

Test execution flow and error handling:

```python
class TestTaskExecutorExecuteTask:
    """Test TaskExecutor.execute_task method."""

    def test_execute_task_success(self, executor, mock_state_manager):
        """Test successful task execution."""
        task = MockTask()
        session = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
        assert result["task_name"] == "CheckRabi"
        mock_state_manager.start_task.assert_called_once_with("CheckRabi", "qubit", "0")
        mock_state_manager.end_task.assert_called_once_with("CheckRabi", "qubit", "0")

    def test_execute_task_always_calls_end_task(self, executor, mock_state_manager):
        """Test execute_task always calls end_task even on failure."""
        task = MockTask()
        task.run = MagicMock(side_effect=RuntimeError("Error"))
        session = MockSession()

        with pytest.raises(TaskExecutionError):
            executor.execute_task(task, session, "0")

        # end_task should always be called (in finally block)
        mock_state_manager.end_task.assert_called_once()
```

### CRScheduler Tests

Test scheduling logic with parameterized tests:

```python
from qdash.workflow.engine.scheduler.cr_utils import group_cr_pairs_by_conflict

@pytest.mark.parametrize(
    "cr_pairs,qid_to_mux,expected_min_groups,reason",
    [
        (["0-1", "2-3"], {"0": 0, "1": 0, "2": 0, "3": 0}, 2, "same MUX conflict"),
        (["0-1", "1-2"], {"0": 0, "1": 0, "2": 0}, 2, "shared qubit conflict"),
        (["0-1", "4-5"], {"0": 0, "1": 0, "4": 1, "5": 1}, 1, "different MUX, no conflicts"),
    ],
)
def test_group_cr_pairs_by_conflict(cr_pairs, qid_to_mux, expected_min_groups, reason):
    """Test CR pair grouping with various conflict scenarios."""
    mux_conflict_map = {}

    groups = group_cr_pairs_by_conflict(cr_pairs, qid_to_mux, mux_conflict_map)

    assert len(groups) >= expected_min_groups, f"Failed: {reason}"

    # Verify no conflicts within groups
    for group in groups:
        qubits_in_group = set()
        for pair in group:
            q1, q2 = pair.split("-")
            assert q1 not in qubits_in_group
            assert q2 not in qubits_in_group
            qubits_in_group.add(q1)
            qubits_in_group.add(q2)

@pytest.mark.parametrize(
    "strategy",
    [
        "largest_first",
        "smallest_last",
        "saturation_largest_first",
    ],
)
def test_coloring_strategies(strategy):
    """Test different coloring strategies produce valid results."""
    cr_pairs = ["0-1", "1-2", "2-3"]
    qid_to_mux = {"0": 0, "1": 0, "2": 0, "3": 0}
    mux_conflict_map = {}

    groups = group_cr_pairs_by_conflict(
        cr_pairs, qid_to_mux, mux_conflict_map, coloring_strategy=strategy
    )

    assert len(groups) >= 2
```

---

## Testing Flow Components

### Context Management Tests

Test thread safety and lifecycle:

```python
class TestThreadSafety:
    """Test thread safety of SessionContext."""

    def test_thread_local_isolation(self):
        """Test that sessions are isolated per thread."""
        context = SessionContext()
        results = {}
        barrier = threading.Barrier(2)

        def thread_func(thread_id, session):
            context.set_session(session)
            barrier.wait()  # Sync threads
            results[thread_id] = context.get_session()

        session1 = MagicMock(name="session1")
        session2 = MagicMock(name="session2")

        thread1 = threading.Thread(target=thread_func, args=("t1", session1))
        thread2 = threading.Thread(target=thread_func, args=("t2", session2))

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        assert results["t1"] is session1
        assert results["t2"] is session2
```

### Context Manager Tests

Test scope-based session management:

```python
def test_session_scope_sets_and_clears(self):
    """Test session_scope context manager."""
    context = SessionContext()
    mock_session = MagicMock()

    with context.session_scope(mock_session) as session:
        assert session is mock_session
        assert context.get_session() is mock_session

    # Session should be cleared after scope
    assert context.get_session() is None

def test_session_scope_restores_previous(self):
    """Test session_scope restores previous session."""
    context = SessionContext()
    session1 = MagicMock(name="session1")
    session2 = MagicMock(name="session2")

    context.set_session(session1)

    with context.session_scope(session2):
        assert context.get_session() is session2

    # Original session should be restored
    assert context.get_session() is session1
```

---

## Testing Helper Functions

### Initialization Tests

Test helper function setup:

```python
class TestFlowSessionInitialization:
    """Test FlowSession initialization and basic setup."""

    def test_flow_session_attributes(self, monkeypatch):
        """Test that FlowSession initializes with correct attributes."""
        # Mock dependencies
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.ExecutionManager",
            MockExecutionManager,
        )
        monkeypatch.setattr(
            "qdash.workflow.helpers.flow_helpers.create_backend",
            lambda **kwargs: MockSession(),
        )

        session = FlowSession(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
            backend="fake",
        )

        assert session.username == "test_user"
        assert session.execution_id == "20240101-001"
        assert session.chip_id == "chip_1"
```

### Global State Tests

Test module-level session management:

```python
class TestGlobalSessionHelpers:
    """Test global session helper functions."""

    def test_init_and_get_session(self, monkeypatch):
        """Test init_calibration and get_session."""
        monkeypatch.setattr(...)

        session1 = init_calibration(
            username="test_user",
            execution_id="20240101-001",
            chip_id="chip_1",
        )

        session2 = get_session()

        assert session1 is session2

    def test_get_session_without_init(self):
        """Test that get_session raises error when no session exists."""
        import qdash.workflow.helpers.flow_helpers as flow_helpers
        flow_helpers._current_session = None

        with pytest.raises(RuntimeError, match="No active calibration session"):
            get_session()
```

---

## Database Testing

### Using InMemory Repositories (Recommended)

For most unit tests, use InMemory repository implementations instead of MongoDB.
This approach is faster, doesn't require database setup, and provides better isolation.

```python
from qdash.workflow.engine.repository import (
    InMemoryExecutionRepository,
    InMemoryChipRepository,
    InMemoryCalibrationNoteRepository,
    InMemoryQubitCalibrationRepository,
    InMemoryCouplingCalibrationRepository,
    InMemoryExecutionCounterRepository,
    InMemoryExecutionLockRepository,
    InMemoryUserRepository,
    InMemoryTaskRepository,
)


class TestWithInMemoryRepositories:
    """Test using InMemory repositories."""

    def test_generate_execution_id(self):
        """Test execution ID generation without MongoDB."""
        from qdash.workflow.service.calib_service import generate_execution_id

        counter_repo = InMemoryExecutionCounterRepository()

        id1 = generate_execution_id(
            username="alice",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )
        id2 = generate_execution_id(
            username="alice",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )

        assert id1.endswith("-000")
        assert id2.endswith("-001")

    def test_scheduler_with_injected_repository(self):
        """Test CRScheduler with InMemory chip repository."""
        from qdash.datamodel.chip import ChipModel
        from qdash.workflow.engine.scheduler import CRScheduler

        chip_repo = InMemoryChipRepository()
        mock_chip = ChipModel(
            chip_id="chip_1",
            username="alice",
            qubits={"0": {}, "1": {}},
            couplings={"0-1": {}},
            # ... other required fields
        )
        chip_repo.add_chip("alice", mock_chip)

        scheduler = CRScheduler(
            username="alice",
            chip_id="chip_1",
            chip_repo=chip_repo,
        )
        # Now scheduler uses InMemory data instead of MongoDB

    def test_service_with_multiple_repositories(self):
        """Test CalibService with multiple InMemory repositories."""
        user_repo = InMemoryUserRepository()
        lock_repo = InMemoryExecutionLockRepository()
        counter_repo = InMemoryExecutionCounterRepository()

        user_repo.add_user("alice", default_project_id="proj-1")

        # Use DI to inject repositories
        # (example pattern, actual implementation may vary)
```

**Benefits of InMemory Testing**:
- No MongoDB setup required
- Faster test execution
- Better test isolation (no shared database state)
- Easy to set up specific test scenarios
- `clear()` method for test setup/teardown

**Test Helper Methods**:

Each InMemory repository provides helper methods for testing:

```python
# Add test data
repo.add_chip("alice", mock_chip)
repo.add_user("alice", default_project_id="proj-1")
repo.add_tasks("alice", ["CheckFreq", "CheckRabi"])

# Clear all data (useful in setup_method)
repo.clear()

# Get all stored data (for assertions)
results = repo.get_all()
```

### Using init_db Fixture

For tests requiring MongoDB:

```python
class TestExecuteTaskIntegration:
    """Integration tests for execute_task method.

    These tests require MongoDB connection (init_db fixture).
    """

    def test_execute_task_records_to_task_result_history(
        self, init_db, mock_task, mock_session, mock_execution_manager, calib_dir
    ):
        """Test execute_task creates TaskResultHistoryDocument."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        mock_task.preprocess.return_value = None
        mock_task.run.return_value = None

        with (...):
            em_result, tm_result = tm.execute_task(...)

        # Verify TaskResultHistoryDocument was created
        task = tm_result.get_task("CheckRabi", "qubit", "0")
        doc = TaskResultHistoryDocument.find_one({"task_id": task.task_id}).run()
        assert doc is not None
        assert doc.name == "CheckRabi"
```

### Isolating Database Tests

Mark tests that need database:

```python
@pytest.mark.usefixtures("init_db")
class TestWithDatabase:
    """Tests that require database connection."""
    pass
```

---

## Assertion Patterns

### State Assertions

Verify object state changes:

```python
def test_start_task_updates_status_to_running(self):
    """Test start_task changes status to RUNNING."""
    tm = TaskManager(...)
    tm._ensure_task_exists("CheckRabi", "qubit", "0")

    tm.start_task("CheckRabi", "qubit", "0")

    task = tm.get_task("CheckRabi", "qubit", "0")
    assert task.status == TaskStatusModel.RUNNING
    assert task.start_at != ""  # Non-empty timestamp
```

### Exception Assertions

Use `pytest.raises` with match patterns:

```python
def test_get_task_raises_for_nonexistent_task(self):
    """Test get_task raises ValueError for unknown task."""
    tm = TaskManager(...)

    with pytest.raises(ValueError, match="Task 'Unknown' not found"):
        tm.get_task("Unknown", "qubit", "0")

def test_execute_task_with_r2_validation_fail(self, ...):
    """Test execute_task with failing R² validation."""
    ...
    with pytest.raises(ValueError, match="R² value too low"):
        tm.execute_task(...)
```

### Mock Assertions

Verify mock interactions:

```python
def test_execute_task_success(self, executor, mock_state_manager):
    """Test successful task execution."""
    task = MockTask()
    session = MockSession()

    result = executor.execute_task(task, session, "0")

    # Verify method calls
    mock_state_manager.start_task.assert_called_once_with("CheckRabi", "qubit", "0")
    mock_state_manager.end_task.assert_called_once_with("CheckRabi", "qubit", "0")

def test_execute_task_calls_preprocess(self, executor, mock_state_manager):
    """Test execute_task calls preprocess and stores input parameters."""
    task = MockTask()
    session = MockSession()

    executor.execute_task(task, session, "0")

    mock_state_manager.put_input_parameters.assert_called_once()
    call_args = mock_state_manager.put_input_parameters.call_args
    assert call_args[0][0] == "CheckRabi"
    assert call_args[0][1] == {"param1": 1.0}
```

### File Assertions

Verify file operations:

```python
def test_save_figures_creates_files(self):
    """Test save_figures creates png and json files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = TaskManager(...)
        fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6])])

        tm.save_figures([fig], "CheckRabi", "qubit", qid="0")

        task = tm.get_task("CheckRabi", "qubit", "0")

        # Check paths are recorded
        assert len(task.figure_path) == 1
        assert len(task.json_figure_path) == 1

        # Check files exist
        png_path = Path(task.figure_path[0])
        json_path = Path(task.json_figure_path[0])
        assert png_path.exists()
        assert json_path.exists()
```

---

## Coverage Guidelines

### Minimum Coverage Targets

| Component             | Target Coverage |
| --------------------- | --------------- |
| Task State Management | 90%             |
| Task Execution        | 85%             |
| Result Processing     | 90%             |
| CR Scheduler          | 85%             |
| Flow Helpers          | 80%             |
| Context Management    | 90%             |

### Required Test Categories

Each component should have tests for:

1. **Initialization**: Constructor behavior, default values
2. **Happy Path**: Normal operation scenarios
3. **Error Handling**: Exception cases, validation failures
4. **Edge Cases**: Empty inputs, boundary conditions
5. **State Transitions**: Lifecycle operations

### Critical Paths to Test

- Task status transitions (SCHEDULED → RUNNING → COMPLETED/FAILED)
- R² validation and rollback behavior
- Fidelity validation (> 100% rejection)
- Parameter propagation (input → output → calib_data)
- File saving with conflict resolution
- Thread-safe context management

---

## Common Pitfalls

### 1. Not Cleaning Up Global State

```python
# Bad - Global state persists between tests
def test_session1(self):
    init_calibration(...)

def test_session2(self):
    get_session()  # May get session from test_session1!

# Good - Clean up in setup
class TestSession:
    def setup_method(self):
        clear_current_session()

    def test_session1(self):
        init_calibration(...)
```

### 2. Using Real Database Without Fixture

```python
# Bad - No database fixture
def test_db_operation(self):
    doc = TaskResultHistoryDocument.find_one({})  # Fails without DB

# Good - Use init_db fixture
def test_db_operation(self, init_db):
    doc = TaskResultHistoryDocument.find_one({})
```

### 3. Insufficient Mock Configuration

```python
# Bad - Mock not fully configured
mock_task = MagicMock()
executor.execute_task(mock_task, session, "0")  # May fail unpredictably

# Good - Configure all required attributes
mock_task = MagicMock()
mock_task.get_name.return_value = "CheckRabi"
mock_task.get_task_type.return_value = "qubit"
mock_task.is_qubit_task.return_value = True
mock_task.r2_threshold = 0.7
```

### 4. Not Testing Error Recovery

```python
# Bad - Only test success
def test_execute_task(self):
    result = executor.execute_task(task, session, "0")
    assert result["success"] is True

# Good - Test error handling and cleanup
def test_execute_task_error_recovery(self):
    task.run.side_effect = RuntimeError("Error")

    with pytest.raises(TaskExecutionError):
        executor.execute_task(task, session, "0")

    # Verify cleanup was performed
    mock_state_manager.end_task.assert_called_once()
```

### 5. Hardcoded Paths in Tests

```python
# Bad - Hardcoded paths
def test_save_data(self):
    tm = TaskManager(..., calib_dir="/tmp/test")  # May conflict

# Good - Use temporary directories
def test_save_data(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = TaskManager(..., calib_dir=tmpdir)
```

---

## Running Tests

### Run All Workflow Tests

```bash
pytest tests/qdash/workflow/ -v
```

### Run Specific Test File

```bash
pytest tests/qdash/workflow/engine/calibration/test_task_manager.py -v
```

### Run Specific Test Class

```bash
pytest tests/qdash/workflow/engine/calibration/test_task_manager.py::TestTaskStateManagement -v
```

### Run With Coverage

```bash
pytest tests/qdash/workflow/ --cov=src/qdash/workflow --cov-report=html
```

### Run Parameterized Tests Only

```bash
pytest tests/qdash/workflow/engine/calibration/test_cr_scheduler.py -v -k "parametrize"
```

