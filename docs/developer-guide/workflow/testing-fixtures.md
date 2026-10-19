# Workflow Test Fixtures and Mocking

Fixtures, mocks, and database setup shared by the workflow tests under `tests/qdash/workflow/`; conventions and how to run the tests are on [Workflow Testing Guidelines](./testing.md).

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

## Database Testing

### Using InMemory Repositories (Recommended)

For most unit tests, use InMemory repository implementations instead of MongoDB.
This approach is faster, doesn't require database setup, and provides better isolation.

```python
from qdash.repository.inmemory import (
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
