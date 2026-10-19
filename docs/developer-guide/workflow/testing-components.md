# Workflow Component Tests

Test examples for the calibration engine, flow context, and flow helper functions, plus the assertion patterns they use; fixtures and mocks referenced here are defined on [Workflow Test Fixtures and Mocking](./testing-fixtures.md).

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
