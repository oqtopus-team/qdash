# Data Models

Pydantic `BaseModel` classes in `src/qdash/datamodel/` that carry calibration data through the
API and workflow; the persisted `Document` classes are listed in [Database Structure](./database-structure.md).

## SystemInfoModel

Base model for common system information.

```python
class SystemInfoModel(BaseModel):
    created_at: str  # ISO8601 timestamp (UTC)
    updated_at: str  # ISO8601 timestamp (UTC)
```

---

## NoteModel

Free-form note attached to a model (qubit, coupling, task result). Embedded
inline on the parent document; an audit row is also written to `note_event`
on every edit.

```python
class NoteModel(BaseModel):
    content: str = ""              # Free-form text
    updated_by: str = ""           # Username of the last editor
    updated_at: datetime | None = None  # None until first set
```

`updated_at = None` distinguishes "never noted" from "noted then cleared".

---

## ProjectModel

Represents a collaborative workspace. Every tenant-visible entity references a project.

```python
class ProjectModel(BaseModel):
    project_id: str        # Globally unique slug/UUID
    owner_user_id: str     # Immutable internal owner ID
    owner_username: str    # Creator/owner of the project
    name: str              # Display name
    description: str | None = None
    tags: list[str] = []   # Optional labels for search
    system_info: SystemInfoModel
```

---

## ProjectMembershipModel

Represents user access to a project.

```python
class ProjectRole(str, Enum):
    """Simplified project permission model."""
    OWNER = "owner"   # Full access (read, write, admin)
    EDITOR = "editor" # Operational write access
    VIEWER = "viewer" # Read-only access

class ProjectMembershipModel(BaseModel):
    project_id: str
    user_id: str
    username: str
    role: ProjectRole
    invited_by_user_id: str | None = None
    invited_by: str | None = None
    status: Literal["pending", "active", "revoked"] = "pending"
    system_info: SystemInfoModel
```

---

## ChipModel

Model representing quantum chip configuration.

```python
class ChipModel(BaseModel):
    chip_id: str           # Chip ID (e.g., "chip1")
    project_id: str        # Owning project ID
    username: str          # Creator's username
    size: int              # Chip size
    qubits: dict[str, QubitModel]      # Qubit map
    couplings: dict[str, CouplingModel] # Coupling map
    installed_at: str      # Installation timestamp
    system_info: SystemInfoModel
```

---

## QubitModel

Model representing an individual qubit.

```python
class QubitModel(BaseModel):
    project_id: str        # Owning project ID
    username: str | None   # Username
    qid: str               # Qubit ID (e.g., "0", "1")
    status: str            # Status ("pending", "completed", etc.)
    chip_id: str | None    # Parent chip ID
    data: dict             # Calibration data
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

## CouplingModel

Model representing coupling between qubits.

```python
class CouplingModel(BaseModel):
    project_id: str        # Owning project ID
    username: str | None   # Username
    qid: str               # Coupling ID (e.g., "0-1")
    status: str            # Status
    chip_id: str | None    # Chip ID
    data: dict             # Calibration data
```

---

## ExecutionModel

Model representing a calibration execution metadata.

> **Note**: `task_results` and `calib_data` were removed to support 256+ qubit systems
> (avoiding MongoDB's 16MB document limit). Task results are stored in `task_result_history`
> collection. Calibration data is stored in `qubit`/`coupling` collections.

```python
class ExecutionStatusModel(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ExecutionModel(BaseModel):
    project_id: str        # Owning project ID
    username: str          # Username (request initiator)
    name: str              # Execution name
    execution_id: str      # Execution ID (e.g., "20240101-001")
    calib_data_path: str   # Calibration data path
    note: dict             # Notes
    status: str            # Status
    tags: list[str]        # Tags
    chip_id: str           # Chip ID
    start_at: datetime     # Start time
    end_at: datetime       # End time
    elapsed_time: timedelta  # Elapsed time
    message: str           # Message
    system_info: SystemInfoModel
```

---

## TaskModel / TaskResultModel

Models for task definitions and execution results.

```python
class TaskStatusModel(str, Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

class RunParameterModel(BaseModel):
    """Experiment configuration parameters (shots, ranges, etc.)."""
    unit: str              # Unit
    value_type: str        # Value type ("float", "int", "np.linspace", etc.)
    value: tuple | int | float | None
    description: str       # Description

class ParameterModel(BaseModel):
    """Calibration parameter model (for both input and output parameters)."""
    value: float | int     # Value
    value_type: str        # Value type
    error: float           # Error
    unit: str              # Unit
    description: str       # Description
    calibrated_at: str     # Calibration timestamp
    execution_id: str      # Execution ID
    task_id: str           # Task ID

class CalibDataModel(BaseModel):
    qubit: dict[str, dict[str, ParameterModel]]     # Per-qubit data
    coupling: dict[str, dict[str, ParameterModel]]  # Per-coupling data

class BaseTaskResultModel(BaseModel):
    project_id: str
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

## BackendModel

Model representing backend configuration.

```python
class BackendModel(BaseModel):
    name: str      # Backend name
    username: str  # Username
```
