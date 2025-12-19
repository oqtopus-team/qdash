# Workflow Engine Architecture

This document explains the architecture of the `qdash.workflow.engine` module,
which provides the core infrastructure for calibration workflow execution.

## Overview

The engine module is responsible for:

- **Task Execution**: Running calibration tasks with proper lifecycle management
- **State Management**: Tracking task status, parameters, and results
- **Execution Tracking**: Managing workflow execution sessions
- **Scheduling**: Coordinating parallel task execution
- **Data Persistence**: Saving results to MongoDB and filesystem
- **Backend Abstraction**: Supporting multiple hardware backends (qubex, fake)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CalibService                              │
│                    (High-level API)                              │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CalibOrchestrator                            │
│               (Session Lifecycle Manager)                        │
│  - Directory structure creation                                  │
│  - Component initialization                                      │
│  - Task execution coordination                                   │
└───────┬─────────────┬──────────────┬────────────────────────────┘
        │             │              │
        ▼             ▼              ▼
┌───────────┐  ┌─────────────┐  ┌──────────┐
│TaskContext│  │ Execution   │  │ Backend  │
│           │  │  Service    │  │          │
└─────┬─────┘  └──────┬──────┘  └────┬─────┘
      │               │              │
      ▼               ▼              ▼
┌───────────────────────────────────────────────────────────────┐
│                       TaskExecutor                             │
│  - Preprocess → Run → Postprocess lifecycle                   │
│  - R² and fidelity validation                                 │
│  - Figure and raw data saving                                 │
└───────┬───────────┬───────────┬───────────┬──────────────────┘
        │           │           │           │
        ▼           ▼           ▼           ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│TaskState     │ │TaskResult    │ │TaskHistory   │ │Filesystem    │
│Manager       │ │Processor     │ │Recorder      │ │CalibData     │
│              │ │              │ │              │ │Saver         │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

## Module Structure

```
engine/
├── __init__.py          # Public API exports
├── orchestrator.py      # CalibOrchestrator - session lifecycle
├── config.py            # CalibConfig - session configuration
├── task_runner.py       # Prefect task wrappers
├── params_updater.py    # Backend parameter updates
├── util.py              # Utility functions
│
├── task/                # Task execution layer
│   ├── context.py       # TaskContext - execution context
│   ├── executor.py      # TaskExecutor - task lifecycle
│   ├── state_manager.py # TaskStateManager - state tracking
│   ├── result_processor.py # Result validation
│   └── history_recorder.py # History recording
│
├── execution/           # Execution management layer
│   ├── service.py       # ExecutionService - session tracking
│   ├── state_manager.py # ExecutionStateManager
│   └── models.py        # Execution data models
│
├── scheduler/           # Scheduling layer
│   ├── cr_scheduler.py  # CRScheduler - 2-qubit scheduling
│   ├── one_qubit_scheduler.py  # 1-qubit scheduling
│   └── plugins.py       # Ordering strategies
│
├── repository/          # Data persistence layer
│   ├── protocols.py     # Repository interfaces
│   ├── mongo_impl.py    # MongoDB implementations
│   ├── mongo_execution.py  # Execution repository
│   └── filesystem_impl.py  # Filesystem implementations
│
└── backend/             # Hardware abstraction layer
    ├── base.py          # BaseBackend abstract class
    ├── factory.py       # Backend factory
    ├── qubex.py         # Qubex backend
    └── fake.py          # Fake backend for testing
```

## Core Components

### 1. CalibOrchestrator

**Location**: `engine/orchestrator.py`

**Purpose**: Manages the complete lifecycle of a calibration session.

**Responsibilities**:
- Creates directory structure for calibration data
- Initializes ExecutionService, TaskContext, and Backend
- Coordinates task execution via `run_task()`
- Handles session completion and failure

**Usage**:
```python
from qdash.workflow.engine import CalibOrchestrator, CalibConfig

config = CalibConfig(
    username="alice",
    chip_id="64Qv3",
    qids=["0", "1"],
    execution_id="20240101-001",
)
orchestrator = CalibOrchestrator(config)
orchestrator.initialize()

# Run tasks
result = orchestrator.run_task("CheckRabi", qid="0")

# Complete session
orchestrator.complete()
```

### 2. TaskContext

**Location**: `engine/task/context.py`

**Purpose**: Container for task execution state and results.

**Key Attributes**:
- `execution_id`: Current execution identifier
- `task_result`: Container for qubit/coupling/global task results
- `calib_data`: Calibration data (parameters extracted from tasks)
- `controller_info`: Hardware controller information

### 3. TaskExecutor

**Location**: `engine/task/executor.py`

**Purpose**: Executes individual calibration tasks with proper lifecycle management.

**Execution Flow**:
```
┌────────────────┐
│  ensure_task   │  Register task in state manager
│    exists      │
└───────┬────────┘
        ▼
┌────────────────┐
│  start_task    │  Set status to RUNNING, record start time
└───────┬────────┘
        ▼
┌────────────────┐
│  preprocess    │  Extract input parameters from backend
└───────┬────────┘
        ▼
┌────────────────┐
│     run        │  Execute hardware measurement
└───────┬────────┘
        ▼
┌────────────────┐
│  postprocess   │  Extract output parameters, generate figures
└───────┬────────┘
        ▼
┌────────────────┐
│ validate_r2    │  Check R² threshold
└───────┬────────┘
        ▼
┌────────────────┐
│ save_artifacts │  Save figures, raw data
└───────┬────────┘
        ▼
┌────────────────┐
│  end_task      │  Record end time, update status
└────────────────┘
```

### 4. TaskStateManager

**Location**: `engine/task/state_manager.py`

**Purpose**: Manages task state transitions and parameter storage.

**State Transitions**:
```
SCHEDULED → RUNNING → COMPLETED
                   ↘ FAILED
```

**Key Methods**:
- `ensure_task_exists()`: Create task entry if not exists
- `start_task()`: Mark task as running
- `put_input_parameters()`: Store input parameters
- `put_output_parameters()`: Store output parameters
- `update_task_status_to_completed()`: Mark success
- `update_task_status_to_failed()`: Mark failure
- `end_task()`: Record end timestamp

### 5. ExecutionService

**Location**: `engine/execution/service.py`

**Purpose**: Manages workflow execution sessions in MongoDB.

**Responsibilities**:
- Creates and tracks execution records
- Updates task results during execution
- Manages execution status (RUNNING, COMPLETED, FAILED)
- Handles tags and metadata

### 6. Schedulers

#### CRScheduler (2-Qubit)

**Location**: `engine/scheduler/cr_scheduler.py`

**Purpose**: Schedules 2-qubit (Cross-Resonance) calibration tasks.

**Features**:
- Graph coloring for conflict avoidance
- MUX-aware parallel grouping
- Multiple coloring strategies

#### OneQubitScheduler (1-Qubit)

**Location**: `engine/scheduler/one_qubit_scheduler.py`

**Purpose**: Schedules 1-qubit calibration tasks.

**Features**:
- Box-aware grouping (BOX_A, BOX_B, BOX_MIXED)
- Synchronized execution mode
- Pluggable ordering strategies

### 7. Repository Layer

**Location**: `engine/repository/`

**Purpose**: Data persistence abstraction.

**Protocols** (interfaces):
- `TaskResultHistoryRepository`: Task result history
- `ChipRepository`: Chip configuration
- `ChipHistoryRepository`: Chip history snapshots
- `CalibDataSaver`: Figure and raw data saving
- `ExecutionRepository`: Execution records

**Implementations**:
- `MongoTaskResultHistoryRepository`: MongoDB implementation
- `MongoChipRepository`: MongoDB implementation
- `FilesystemCalibDataSaver`: Local filesystem

### 8. Backend Layer

**Location**: `engine/backend/`

**Purpose**: Hardware abstraction.

**BaseBackend Interface**:
```python
class BaseBackend(ABC):
    name: str

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def get_instance(self) -> Any: ...

    @abstractmethod
    def save_note(...) -> None: ...

    @abstractmethod
    def update_note(...) -> None: ...
```

**Implementations**:
- `QubexBackend`: Real hardware via qubex library
- `FakeBackend`: Simulation for testing

## Data Flow

### Task Execution Data Flow

```
┌──────────┐     ┌────────────────┐     ┌──────────────┐
│ Backend  │────▶│ PreProcessResult │────▶│ input_params │
│(hardware)│     │ (from backend)   │     │ (stored)     │
└──────────┘     └────────────────┘     └──────────────┘
     │
     ▼
┌──────────┐     ┌────────────────┐     ┌──────────────┐
│  Run     │────▶│   RunResult    │────▶│   R² value   │
│(measure) │     │ (raw_result)   │     │ (validated)  │
└──────────┘     └────────────────┘     └──────────────┘
     │
     ▼
┌──────────┐     ┌──────────────────┐   ┌──────────────┐
│ Postproc │────▶│ PostProcessResult│──▶│output_params │
│          │     │ (params,figures) │   │figures,data  │
└──────────┘     └──────────────────┘   └──────────────┘
```

### Persistence Flow

```
TaskExecutor
     │
     ├──▶ TaskStateManager ──▶ In-memory state
     │
     ├──▶ TaskHistoryRecorder ──▶ MongoDB (TaskResultHistoryDocument)
     │
     ├──▶ FilesystemCalibDataSaver ──▶ Local files (fig/, raw_data/)
     │
     └──▶ ExecutionService ──▶ MongoDB (ExecutionDocument)
```

## Extension Points

### Adding a New Backend

1. Create `engine/backend/your_backend.py`:
```python
from qdash.workflow.engine.backend.base import BaseBackend

class YourBackend(BaseBackend):
    name = "your_backend"

    def connect(self) -> None:
        # Initialize hardware connection
        pass

    def get_instance(self) -> Any:
        # Return experiment session
        pass
```

2. Register in `engine/backend/factory.py`

### Adding a New Scheduler Strategy

1. Implement the strategy in `engine/scheduler/plugins.py`
2. Register in the scheduler's strategy registry

### Adding a New Repository Implementation

1. Implement the protocol from `engine/repository/protocols.py`
2. Use dependency injection in the component that needs it

## Best Practices

### For Engine Developers

1. **Use Protocols**: Define interfaces before implementations
2. **Dependency Injection**: Pass repositories/services as constructor args
3. **State Isolation**: Don't share mutable state between tasks
4. **Error Handling**: Always update task status on failure
5. **Logging**: Use structured logging for debugging

### For Service Users

1. **Use CalibService**: Don't directly instantiate engine components
2. **Handle Exceptions**: Catch `TaskExecutionError`, `R2ValidationError`
3. **Check Results**: Verify task success before proceeding

## Related Documentation

- [Testing Guidelines](./testing.md): How to test workflow components
- [CalibService API](../../../src/qdash/workflow/__init__.py): High-level API
