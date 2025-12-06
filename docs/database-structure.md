# QDash Database Structure Documentation

This document describes the database structure of the QDash project. QDash uses MongoDB as its primary database, managing data through the Bunnet ODM (Object Document Mapper).

## Overview

The QDash data model consists of two layers:

1. **datamodel** (`src/qdash/datamodel/`) - Business logic data models using Pydantic BaseModel
2. **dbmodel** (`src/qdash/dbmodel/`) - Database persistence document models using Bunnet Document

---

## MongoDB Collections

| Collection | Document Class | Description |
|------------|----------------|-------------|
| `chip` | ChipDocument | Quantum chip configuration |
| `qubit` | QubitDocument | Individual qubit data |
| `coupling` | CouplingDocument | Qubit coupling information |
| `execution_history` | ExecutionHistoryDocument | Calibration execution history |
| `task_result_history` | TaskResultHistoryDocument | Task result history |
| `qubit_history` | QubitHistoryDocument | Daily qubit snapshots |
| `chip_history` | ChipHistoryDocument | Daily chip snapshots |
| `coupling_history` | CouplingHistoryDocument | Daily coupling snapshots |
| `task` | TaskDocument | Task definitions |
| `backend` | BackendDocument | Backend configurations |
| `user` | UserDocument | User authentication |
| `tag` | TagDocument | Tag management |
| `execution_lock` | ExecutionLockDocument | Exclusive execution lock |
| `execution_counter` | ExecutionCounterDocument | Execution ID counter |
| `calibration_note` | CalibrationNoteDocument | Calibration notes |
| `flows` | FlowDocument | User-defined flows |

---

## Data Models (datamodel)

### SystemInfoModel

Base model for common system information.

```python
class SystemInfoModel(BaseModel):
    created_at: str  # ISO8601 timestamp (Asia/Tokyo)
    updated_at: str  # ISO8601 timestamp (Asia/Tokyo)
```

---

### ChipModel

Model representing quantum chip configuration.

```python
class ChipModel(BaseModel):
    chip_id: str           # Chip ID (e.g., "chip1")
    username: str          # Creator's username
    size: int              # Chip size
    qubits: dict[str, QubitModel]      # Qubit map
    couplings: dict[str, CouplingModel] # Coupling map
    installed_at: str      # Installation timestamp
    system_info: SystemInfoModel
```

---

### QubitModel

Model representing an individual qubit.

```python
class PositionModel(BaseModel):
    x: float  # X coordinate
    y: float  # Y coordinate

class NodeInfoModel(BaseModel):
    position: PositionModel  # Display position

class QubitModel(BaseModel):
    username: str | None   # Username
    qid: str               # Qubit ID (e.g., "0", "1")
    status: str            # Status ("pending", "completed", etc.)
    chip_id: str | None    # Parent chip ID
    data: dict             # Calibration data
    best_data: dict        # Best calibration results
    node_info: NodeInfoModel  # UI display information
```

**Example data field structure:**
```json
{
    "qubit_frequency": {
        "value": 5.0,
        "value_type": "float",
        "error": 0.001,
        "unit": "GHz",
        "description": "Qubit resonance frequency",
        "calibrated_at": "2024-01-01T00:00:00+09:00",
        "execution_id": "20240101-001",
        "task_id": "uuid-xxx"
    }
}
```

---

### CouplingModel

Model representing coupling between qubits.

```python
class EdgeInfoModel(BaseModel):
    source: str   # Source node ID
    target: str   # Target node ID
    size: int     # Edge size
    fill: str     # Fill color

class CouplingModel(BaseModel):
    username: str | None   # Username
    qid: str               # Coupling ID (e.g., "0-1")
    status: str            # Status
    chip_id: str | None    # Chip ID
    data: dict             # Calibration data
    best_data: dict        # Best calibration results
    edge_info: EdgeInfoModel  # UI display information
```

---

### ExecutionModel

Model representing a calibration execution.

```python
class ExecutionStatusModel(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class ExecutionModel(BaseModel):
    username: str          # Username
    name: str              # Execution name
    execution_id: str      # Execution ID (e.g., "20240101-001")
    calib_data_path: str   # Calibration data path
    note: dict             # Notes
    status: str            # Status
    task_results: dict[str, TaskResultModel]  # Task results
    tags: list[str]        # Tags
    controller_info: dict  # Controller information
    fridge_info: dict      # Fridge information
    chip_id: str           # Chip ID
    start_at: str          # Start time
    end_at: str            # End time
    elapsed_time: str      # Elapsed time
    calib_data: CalibDataModel  # Calibration data
    message: str           # Message
    system_info: SystemInfoModel
```

---

### TaskModel / TaskResultModel

Models for task definitions and execution results.

```python
class TaskStatusModel(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"

class InputParameterModel(BaseModel):
    unit: str              # Unit
    value_type: str        # Value type ("float", "int", "np.linspace", etc.)
    value: tuple | int | float | None
    description: str       # Description

class OutputParameterModel(BaseModel):
    value: float | int     # Value
    value_type: str        # Value type
    error: float           # Error
    unit: str              # Unit
    description: str       # Description
    calibrated_at: str     # Calibration timestamp
    execution_id: str      # Execution ID
    task_id: str           # Task ID

class CalibDataModel(BaseModel):
    qubit: dict[str, dict[str, OutputParameterModel]]     # Per-qubit data
    coupling: dict[str, dict[str, OutputParameterModel]]  # Per-coupling data

class BaseTaskResultModel(BaseModel):
    task_id: str           # UUID
    name: str              # Task name
    upstream_id: str       # Upstream task ID
    status: TaskStatusModel
    message: str           # Message
    input_parameters: dict
    output_parameters: dict
    output_parameter_names: list[str]
    note: dict
    figure_path: list[str]     # Figure paths
    json_figure_path: list[str]  # JSON figure paths
    raw_data_path: list[str]   # Raw data paths
    start_at: str
    end_at: str
    elapsed_time: str
    task_type: str         # "global", "qubit", "coupling", "system"
    system_info: SystemInfoModel

# Task type subclasses
class SystemTaskModel(BaseTaskResultModel):
    task_type: Literal["system"] = "system"

class GlobalTaskModel(BaseTaskResultModel):
    task_type: Literal["global"] = "global"

class QubitTaskModel(BaseTaskResultModel):
    task_type: Literal["qubit"] = "qubit"
    qid: str  # Target qubit ID

class CouplingTaskModel(BaseTaskResultModel):
    task_type: Literal["coupling"] = "coupling"
    qid: str  # Target coupling ID

class TaskResultModel(BaseModel):
    system_tasks: list[SystemTaskModel]
    global_tasks: list[GlobalTaskModel]
    qubit_tasks: dict[str, list[QubitTaskModel]]
    coupling_tasks: dict[str, list[CouplingTaskModel]]

class TaskModel(BaseModel):
    username: str
    name: str              # Task name (e.g., "CheckT1", "CheckT2Echo")
    backend: str | None    # Backend name
    description: str
    task_type: str         # "global", "qubit", "coupling"
    input_parameters: dict
    output_parameters: dict
```

---

### BackendModel

Model representing backend configuration.

```python
class BackendModel(BaseModel):
    name: str      # Backend name
    username: str  # Username
```

---

### FridgeModel

Model representing fridge data.

```python
class FridgeModel(BaseModel):
    device_id: str          # Device ID
    timestamp: datetime     # Timestamp
    data: dict              # Data
    system_info: SystemInfoModel
```

---

## Database Documents (dbmodel)

### ChipDocument

**Collection:** `chip`

**Indexes:**
- `(chip_id, username)` - Unique compound index

```python
class ChipDocument(Document):
    chip_id: str = "SAMPLE"
    username: str
    size: int = 64
    qubits: dict[str, QubitModel] = {}
    couplings: dict[str, CouplingModel] = {}
    installed_at: str  # ISO8601
    system_info: SystemInfoModel
```

**Key Methods:**
- `get_current_chip(username)` - Get the most recently installed chip
- `get_chip_by_id(username, chip_id)` - Get a specific chip
- `update_qubit(qid, qubit_data)` - Update a qubit
- `update_coupling(qid, coupling_data)` - Update a coupling

---

### QubitDocument

**Collection:** `qubit`

**Indexes:**
- `(chip_id, qid, username)` - Unique compound index

```python
class QubitDocument(Document):
    username: str
    qid: str
    status: str = "pending"
    chip_id: str
    data: dict
    best_data: dict = {}
    node_info: NodeInfoModel
    system_info: SystemInfoModel
```

**Fidelity Metrics (tracked in best_data):**
- `average_readout_fidelity`
- `readout_fidelity_0`, `readout_fidelity_1`
- `x90_gate_fidelity`, `x180_gate_fidelity`
- `t1`, `t2_echo`, `t2_star`

**Key Methods:**
- `update_calib_data(username, qid, chip_id, output_parameters)` - Update calibration data
- `update_status(qid, chip_id, status)` - Update status

---

### CouplingDocument

**Collection:** `coupling`

**Indexes:**
- `(chip_id, qid, username)` - Unique compound index

```python
class CouplingDocument(Document):
    username: str
    qid: str               # Coupling ID (e.g., "0-1")
    status: str = "pending"
    chip_id: str
    data: dict
    best_data: dict = {}
    edge_info: EdgeInfoModel
    system_info: SystemInfoModel
```

**Fidelity Metrics (tracked in best_data):**
- `zx90_gate_fidelity`
- `bell_state_fidelity`

---

### ExecutionHistoryDocument

**Collection:** `execution_history`

**Indexes:**
- `(execution_id, username)` - Unique compound index

```python
class ExecutionHistoryDocument(Document):
    username: str
    name: str
    execution_id: str
    calib_data_path: str
    note: dict
    status: str
    task_results: dict[str, TaskResultModel]
    tags: list[str]
    controller_info: dict
    fridge_info: dict
    chip_id: str
    start_at: str
    end_at: str
    elapsed_time: str
    calib_data: dict
    message: str
    system_info: SystemInfoModel
```

**Key Methods:**
- `from_execution_model(execution_model)` - Create from ExecutionModel
- `upsert_document(execution_model)` - Upsert operation

---

### TaskResultHistoryDocument

**Collection:** `task_result_history`

**Indexes:**
- `(task_id, username)` - Unique compound index

```python
class TaskResultHistoryDocument(Document):
    username: str
    task_id: str
    name: str
    upstream_id: str
    status: str
    message: str
    input_parameters: dict
    output_parameters: dict
    output_parameter_names: list[str]
    note: dict
    figure_path: list[str]
    json_figure_path: list[str]
    raw_data_path: list[str]
    start_at: str
    end_at: str
    elapsed_time: str
    task_type: str
    system_info: SystemInfoModel
    qid: str = ""
    execution_id: str
    tags: list[str]
    chip_id: str
```

---

### QubitHistoryDocument

**Collection:** `qubit_history`

**Indexes:**
- `(chip_id, qid, username, recorded_date)` - Unique compound index

Daily snapshot history table.

```python
class QubitHistoryDocument(Document):
    username: str
    qid: str
    status: str
    chip_id: str
    data: dict
    best_data: dict = {}
    node_info: NodeInfoModel
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

### ChipHistoryDocument

**Collection:** `chip_history`

**Indexes:**
- `(chip_id, username, recorded_date)` - Unique compound index

```python
class ChipHistoryDocument(Document):
    chip_id: str
    username: str
    size: int
    qubits: dict[str, QubitModel]
    couplings: dict[str, CouplingModel]
    installed_at: str
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

### CouplingHistoryDocument

**Collection:** `coupling_history`

**Indexes:**
- `(chip_id, qid, username, recorded_date)` - Unique compound index

```python
class CouplingHistoryDocument(Document):
    username: str
    qid: str
    status: str
    chip_id: str
    data: dict
    best_data: dict = {}
    edge_info: EdgeInfoModel
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

### TaskDocument

**Collection:** `task`

**Indexes:**
- `(name, username)` - Unique compound index

Stores task definition information.

```python
class TaskDocument(Document):
    username: str
    name: str              # Task name (e.g., "CheckT1")
    backend: str | None
    description: str
    task_type: str         # "global", "qubit", "coupling"
    input_parameters: dict | None
    output_parameters: dict | None
```

---

### BackendDocument

**Collection:** `backend`

**Indexes:**
- `(name, username)` - Unique compound index

```python
class BackendDocument(Document):
    username: str
    name: str
    system_info: SystemInfoModel
```

---

### UserDocument

**Collection:** `user`

**Indexes:**
- `username` - Unique index
- `access_token` - Unique index

```python
class UserDocument(Document):
    username: str
    hashed_password: str
    access_token: str
    full_name: str | None = None
    disabled: bool = False
    system_info: SystemInfoModel
```

---

### TagDocument

**Collection:** `tag`

**Indexes:**
- `(name, username)` - Unique compound index

```python
class TagDocument(Document):
    username: str
    name: str
```

---

### ExecutionLockDocument

**Collection:** `execution_lock`

Singleton document for exclusive execution control. Ensures only one calibration runs at a time.

```python
class ExecutionLockDocument(Document):
    locked: bool = False
    system_info: SystemInfoModel
```

**Key Methods:**
- `get_lock_status()` - Get lock status
- `lock()` - Acquire lock
- `unlock()` - Release lock

---

### ExecutionCounterDocument

**Collection:** `execution_counter`

**Indexes:**
- `(date, username, chip_id)` - Unique compound index

Manages execution ID sequence numbers per date/user/chip.

```python
class ExecutionCounterDocument(Document):
    date: str           # YYYYMMDD format
    username: str
    chip_id: str
    index: int          # Sequence number (starts from 0)
    system_info: SystemInfoModel
```

**Key Methods:**
- `get_next_index(date, username, chip_id)` - Atomically get next index

Generated execution ID format: `YYYYMMDD-NNN` (e.g., `20240101-001`)

---

### CalibrationNoteDocument

**Collection:** `calibration_note`

**Indexes:**
- `(execution_id, task_id, username, chip_id)` - Unique compound index
- `(chip_id, timestamp)` - Search index

```python
class CalibrationNoteDocument(Document):
    username: str
    chip_id: str
    execution_id: str
    task_id: str
    note: dict
    timestamp: str  # ISO8601
    system_info: SystemInfoModel
```

---

### FlowDocument

**Collection:** `flows`

**Indexes:**
- `(username, name)` - Unique per user
- `(username, created_at)` - For sorted listing

Stores metadata for user-defined Python flows (custom calibration workflows).

```python
class FlowDocument(Document):
    name: str              # Flow name
    username: str
    chip_id: str           # Target chip ID
    description: str = ""
    flow_function_name: str  # Entry point function name
    default_parameters: dict = {}
    file_path: str         # Relative path to .py file
    deployment_id: str | None = None  # Prefect deployment ID
    created_at: datetime
    updated_at: datetime
    tags: list[str] = []
```

---

## Entity Relationship Diagram (Conceptual)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│     User     │     │    Chip      │     │  Execution   │
│              │─────│              │─────│   History    │
│  username*   │  1:n│  chip_id*    │  1:n│execution_id* │
│  password    │     │  username    │     │  username    │
│  token       │     │  size        │     │  chip_id     │
└──────────────┘     │  qubits      │     │  status      │
                     │  couplings   │     │  task_results│
                     └──────────────┘     └──────────────┘
                            │                    │
                     ┌──────┴──────┐             │
                     ▼             ▼             ▼
              ┌──────────┐  ┌──────────┐  ┌─────────────┐
              │  Qubit   │  │ Coupling │  │ TaskResult  │
              │          │  │          │  │  History    │
              │   qid*   │  │   qid*   │  │             │
              │  chip_id │  │  chip_id │  │  task_id*   │
              │   data   │  │   data   │  │execution_id │
              │ best_data│  │ best_data│  │   status    │
              └──────────┘  └──────────┘  └─────────────┘
                    │              │
                    ▼              ▼
           ┌─────────────┐ ┌─────────────┐
           │QubitHistory │ │CouplingHist │
           │             │ │             │
           │recorded_date│ │recorded_date│
           │    data     │ │    data     │
           └─────────────┘ └─────────────┘

         ┌─────────────┐  ┌─────────────┐
         │    Task     │  │   Backend   │
         │             │  │             │
         │   name*     │  │   name*     │
         │  username   │  │  username   │
         │ task_type   │  └─────────────┘
         │input_params │
         │output_params│
         └─────────────┘

         ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
         │    Tag      │  │ Exec Lock   │  │Exec Counter │
         │             │  │             │  │             │
         │   name*     │  │   locked    │  │   date*     │
         │  username   │  │             │  │ username*   │
         └─────────────┘  └─────────────┘  │  chip_id*   │
                                           │   index     │
         ┌─────────────┐  ┌─────────────┐  └─────────────┘
         │  Calib Note │  │    Flow     │
         │             │  │             │
         │execution_id*│  │   name*     │
         │  task_id*   │  │  username*  │
         │    note     │  │ file_path   │
         └─────────────┘  └─────────────┘

* = Primary Key or part of Unique Index
```

---

## Data Flow

### During Calibration Execution

1. Acquire lock via **ExecutionLock**
2. Generate execution ID from **ExecutionCounter** (YYYYMMDD-NNN)
3. Execute each task:
   - Save task results to **TaskResultHistoryDocument**
   - Update calibration data in **QubitDocument** / **CouplingDocument**
   - Save history to **QubitHistoryDocument** / **CouplingHistoryDocument**
4. Save overall results to **ExecutionHistoryDocument**
5. Save chip snapshot to **ChipHistoryDocument**
6. Release **ExecutionLock**

### Best Data Update Logic

The `best_data` field tracks the best fidelity metrics:

- **Qubit**: `average_readout_fidelity`, `readout_fidelity_0/1`, `x90/x180_gate_fidelity`, `t1`, `t2_echo`, `t2_star`
- **Coupling**: `zx90_gate_fidelity`, `bell_state_fidelity`

Values are only updated when new calibration results exceed existing values.

---

## Timezone

All timestamps are managed in **Asia/Tokyo (JST)** timezone.

- `created_at`, `updated_at`: ISO8601 format
- `recorded_date`: YYYYMMDD format
- `calibrated_at`: ISO8601 format
