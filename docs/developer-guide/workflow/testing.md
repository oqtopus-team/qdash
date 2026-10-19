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
- **Database**: MongoDB via init_db fixture (shared conftest.py), or InMemory repositories for unit tests

Fixtures, mocks, and database setup are on [Workflow Test Fixtures and Mocking](./testing-fixtures.md). Examples for each component and the assertion patterns they use are on [Workflow Component Tests](./testing-components.md).

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

| Source Path                                                   | Test Path                                                         |
| ------------------------------------------------------------- | ----------------------------------------------------------------- |
| `src/qdash/workflow/engine/task/executor.py`                  | `tests/qdash/workflow/engine/task/test_executor.py`               |
| `src/qdash/workflow/engine/task/result_processor.py`          | `tests/qdash/workflow/engine/task/test_result_processor.py`       |
| `src/qdash/workflow/engine/task/state_manager/manager.py`     | `tests/qdash/workflow/engine/task/test_state_manager.py`          |
| `src/qdash/workflow/engine/execution/service.py`              | `tests/qdash/workflow/engine/execution/test_service.py`           |
| `src/qdash/workflow/engine/scheduler/cr_scheduler.py`         | `tests/qdash/workflow/engine/scheduler/test_cr_scheduler.py`      |
| `src/qdash/workflow/engine/scheduler/one_qubit_scheduler.py`  | `tests/qdash/workflow/engine/scheduler/test_one_qubit_scheduler.py` |
| `src/qdash/workflow/service/context.py`                       | `tests/qdash/workflow/service/test_context.py`                    |
| `src/qdash/workflow/service/session.py`                       | `tests/qdash/workflow/service/test_session.py`                    |

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

Use `snake_case` with the `test_` prefix. Include the action and expected outcome:

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

## Running Tests

### Run All Workflow Tests

```bash
pytest tests/qdash/workflow/ -v
```

### Run Specific Test File

```bash
pytest tests/qdash/workflow/engine/task/test_state_manager.py -v
```

### Run Specific Test Class

```bash
pytest tests/qdash/workflow/engine/task/test_state_manager.py::TestTaskStatusTransitions -v
```

### Run With Coverage

```bash
pytest tests/qdash/workflow/ --cov=src/qdash/workflow --cov-report=html
```

### Run Parameterized Tests Only

```bash
pytest tests/qdash/workflow/engine/scheduler/test_cr_scheduler.py -v -k "parametrize"
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

Each component should have tests for (examples: [Workflow Component Tests](./testing-components.md)):

1. **Initialization**: Constructor behavior, default values
2. **Happy Path**: Normal operation scenarios
3. **Error Handling**: Exception cases, validation failures
4. **Edge Cases**: Empty inputs, boundary conditions
5. **State Transitions**: Lifecycle operations

### Critical Paths to Test

- Task status transitions (SCHEDULED → RUNNING → COMPLETED/FAILED/CANCELLED)
- Cancellation handling (on_cancellation hook, status updates, lock release)
- R² validation and rollback behavior
- Fidelity validation (> 100% rejection)
- Parameter propagation (input → output → calib_data)
- File saving with conflict resolution
- Thread-safe context management

---

## Common Pitfalls

### Not Cleaning Up Global State

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

### Using Real Database Without Fixture

See [Database Testing](./testing-fixtures.md#database-testing) for the InMemory alternative.

```python
# Bad - No database fixture
def test_db_operation(self):
    doc = TaskResultHistoryDocument.find_one({})  # Fails without DB

# Good - Use init_db fixture
def test_db_operation(self, init_db):
    doc = TaskResultHistoryDocument.find_one({})
```

### Insufficient Mock Configuration

See [Fixture Patterns](./testing-fixtures.md#fixture-patterns) for complete mock fixtures.

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

### Not Testing Error Recovery

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

### Hardcoded Paths in Tests

```python
# Bad - Hardcoded paths
def test_save_data(self):
    tm = TaskManager(..., calib_dir="/tmp/test")  # May conflict

# Good - Use temporary directories
def test_save_data(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        tm = TaskManager(..., calib_dir=tmpdir)
```
