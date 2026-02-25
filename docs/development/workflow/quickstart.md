# Workflow Engine Quickstart

This guide helps you get started with the QDash workflow engine.

## Overview

The workflow engine executes calibration tasks using [Prefect](https://www.prefect.io/).
For detailed architecture, see [Engine Architecture](./engine-architecture.md).

## Key Components

```
workflow/
├── engine/           # Core execution engine
│   ├── orchestrator.py   # Session lifecycle (start here)
│   ├── task_runner.py    # Prefect task wrappers
│   └── task/             # Task execution layer
├── calibtasks/       # Calibration task definitions
└── service/          # High-level service APIs
```

## Basic Usage

### 1. Running a Calibration Session

```python
from qdash.workflow.engine import CalibOrchestrator, CalibConfig

# Configure the session
config = CalibConfig(
    username="alice",
    chip_id="64Qv3",
    qids=["0", "1"],
    execution_id="20240101-001",
)

# Initialize and run
orchestrator = CalibOrchestrator(config)
orchestrator.initialize()

# Execute a task
result = orchestrator.run_task("CheckRabi", qid="0")

# Complete the session
orchestrator.complete()
```

### 2. Understanding the Execution Flow

1. `CalibOrchestrator.initialize()` - Creates directories, connects to backend
2. `orchestrator.run_task()` - Executes a single calibration task
3. `orchestrator.complete()` - Finalizes session, saves results to MongoDB

## Adding a New Calibration Task

1. Create a task class in `workflow/calibtasks/`:

```python
from qdash.workflow.calibtasks.base import BaseTask

class MyNewTask(BaseTask):
    name = "MyNewTask"
    
    def preprocess(self, backend):
        # Extract input parameters
        pass
    
    def run(self, backend):
        # Execute measurement
        pass
    
    def postprocess(self, backend, result):
        # Process results, generate figures
        pass
```

2. Register it in `workflow/calibtasks/active_protocols.py`

## Testing

Use the `FakeBackend` for testing without hardware:

```python
config = CalibConfig(
    backend_name="fake",  # Use fake backend
    ...
)
```

See [Testing Guidelines](./testing.md) for more details.

## Cancellation Support

All top-level `@flow` decorators must register the `on_flow_cancellation` hook to support cancellation from the UI:

```python
from qdash.workflow.service.calib_service import on_flow_cancellation

@flow(on_cancellation=[on_flow_cancellation])
def my_calibration_flow(
    username: str,
    chip_id: str,
    project_id: str | None = None,
    flow_name: str | None = None,
    ...
):
    cal = CalibService(username, chip_id, ...)
    try:
        # ... run tasks ...
        cal.finish_calibration()
    except BaseException as e:
        from qdash.workflow.service.calib_service import _is_cancellation
        if _is_cancellation(e):
            cal.cancel_calibration()
        else:
            cal.fail_calibration(str(e))
        raise
```

When cancelled, Prefect kills the process with SIGTERM and runs the `on_cancellation` hook. The hook updates the execution and task statuses to `cancelled` and releases the execution lock.

See [Engine Architecture — Cancellation](./engine-architecture.md#cancellation) for implementation details.

## Next Steps

- [Engine Architecture](./engine-architecture.md) - Deep dive into components
- [Testing Guidelines](./testing.md) - How to test workflow code
