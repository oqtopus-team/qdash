# Database Structure

QDash uses MongoDB via the Bunnet ODM with a project-centric multi-tenant model. The data model has two layers:

- **datamodel** (`src/qdash/datamodel/`) — Pydantic `BaseModel` for business logic
- **dbmodel** (`src/qdash/dbmodel/`) — Bunnet `Document` for database persistence

## MongoDB Collections

| Collection            | Document Class            | Description                                     |
| --------------------- | ------------------------- | ----------------------------------------------- |
| `project`             | ProjectDocument           | Project metadata (owner-centric workspace)      |
| `project_membership`  | ProjectMembershipDocument | User membership & role per project              |
| `chip`                | ChipDocument              | Quantum chip configuration scoped to a project  |
| `qubit`               | QubitDocument             | Individual qubit data                           |
| `coupling`            | CouplingDocument          | Qubit coupling information                      |
| `execution_history`   | ExecutionHistoryDocument  | Calibration execution history                   |
| `task_result_history` | TaskResultHistoryDocument | Task result history                             |
| `qubit_history`       | QubitHistoryDocument      | Daily qubit snapshots                           |
| `chip_history`        | ChipHistoryDocument       | Daily chip snapshots                            |
| `coupling_history`    | CouplingHistoryDocument   | Daily coupling snapshots                        |
| `task`                | TaskDocument              | Task definitions                                |
| `backend`             | BackendDocument           | Backend configurations (project scoped)         |
| `user`                | UserDocument              | User authentication / default project bootstrap |
| `tag`                 | TagDocument               | Project-level tag management                    |
| `execution_lock`      | ExecutionLockDocument     | Exclusive execution lock                        |
| `execution_counter`   | ExecutionCounterDocument  | Execution ID counter                            |
| `calibration_note`    | CalibrationNoteDocument   | Calibration notes (workflow internal)           |
| `flows`               | FlowDocument              | User-defined flows                              |
| `metric_note`         | MetricNoteDocument        | Legacy dashboard metric notes scoped by cooldown/range |
| `chip_note`           | ChipNoteDocument          | Dashboard chip notes scoped by cooldown/range          |
| `target_note`         | TargetNoteDocument        | Dashboard pinned target summaries scoped by cooldown/range |
| `note_event`          | NoteEventDocument         | Audit log for every note edit (write-through)   |
| `cryostat`            | CryostatDocument          | Cryostat (dilution refrigerator) entity         |
| `cooldown`            | CooldownDocument          | One cool-down cycle of one cryostat             |

---

## Data Models (datamodel)

### SystemInfoModel

Base model for common system information.

```python
class SystemInfoModel(BaseModel):
    created_at: str  # ISO8601 timestamp (UTC)
    updated_at: str  # ISO8601 timestamp (UTC)
```

---

### NoteModel

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

### ProjectModel

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

### ProjectMembershipModel

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

### ChipModel

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

### QubitModel

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

### CouplingModel

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

### ExecutionModel

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

### BackendModel

Model representing backend configuration.

```python
class BackendModel(BaseModel):
    name: str      # Backend name
    username: str  # Username
```

---

## Database Documents (dbmodel)

### ProjectDocument

**Collection:** `project`

**Indexes:**

- `project_id` - Unique identifier per project
- `(owner_user_id, name)` - Efficient owner lookup by immutable user ID
- `(owner_username, name)` - Prevent duplicate names per owner

```python
class ProjectDocument(Document):
    project_id: str            # UUID/slug
    owner_user_id: str         # Immutable internal owner ID
    owner_username: str
    name: str
    description: str | None = None
    tags: list[str] = []
    system_info: SystemInfoModel
```

---

### ProjectMembershipDocument

**Collection:** `project_membership`

**Indexes:**

- `(project_id, username)` - Unique membership per user/project
- `(project_id, user_id)` - Membership lookup by immutable user ID
- `(user_id, status)` - Efficient active membership lookup
- `(username, status)` - Efficient lookup of invitations

```python
class ProjectMembershipDocument(Document):
    project_id: str
    user_id: str
    username: str
    role: ProjectRole
    status: Literal["pending", "active", "revoked"] = "pending"
    invited_by_user_id: str | None = None
    invited_by: str | None = None
    last_accessed_at: str | None = None
    system_info: SystemInfoModel
```

---

### ChipDocument

**Collection:** `chip`

**Indexes:**

- `(project_id, chip_id)` - Unique compound index
- `(username, chip_id)` - Backward-compat lookup while migrating

```python
class ChipDocument(Document):
    project_id: str
    username: str                # Creator/owner username
    chip_id: str = "SAMPLE"
    size: int = 64
    current_cooldown_id: str | None = None  # Cool-down the chip is currently loaded in
    qubits: dict[str, QubitModel] = {}
    couplings: dict[str, CouplingModel] = {}
    installed_at: str  # ISO8601
    note: NoteModel              # Legacy global chip note
    system_info: SystemInfoModel
```

**Editable via** `PATCH /chips/{chip_id}` (topology_id, legacy global note). Dashboard-scoped chip notes are edited via `GET/PUT/DELETE /chips/{chip_id}/note` with `cooldown_id` or a time range. **Deletable via** `DELETE /chips/{chip_id}` (refuses if qubits/couplings exist; `?force=true` cascades). Use `GET /chips/{chip_id}/deletion-impact` for a preflight count before deleting.

**Key Methods:**

- `get_current_chip(project_id)` - Get the most recently installed chip per project
- `get_chip_by_id(project_id, chip_id)` - Get a specific chip
- `update_qubit(qid, qubit_data)` - Update a qubit
- `update_coupling(qid, coupling_data)` - Update a coupling

---

### QubitDocument

**Collection:** `qubit`

**Indexes:**

- `(project_id, chip_id, qid)` - Unique compound index
- `(project_id, username)` - Filter by project/member

```python
class QubitDocument(Document):
    project_id: str
    username: str
    qid: str
    status: str = "pending"
    chip_id: str
    data: dict
    note: NoteModel = NoteModel()                  # Free-form per-qubit note
    metric_notes: dict[str, NoteModel] = {}        # Legacy global per-metric notes
    system_info: SystemInfoModel
```

**Key Methods:**

- `update_calib_data(username, qid, chip_id, output_parameters)` - Update calibration data
- `update_status(qid, chip_id, status)` - Update status

**Note Fields:**

- `note` - Legacy global free-form note about the qubit itself. Scoped dashboard pinned summaries are stored in `TargetNoteDocument` when `PUT /chips/{chip}/qubits/{qid}/note` includes `cooldown_id` or a time range.
- `metric_notes[metric_key]` - Legacy global per-metric annotations. Existing scoped per-metric notes are stored in `MetricNoteDocument`; new dashboard notes should use pinned summaries or forum discussions.

---

### CouplingDocument

**Collection:** `coupling`

**Indexes:**

- `(project_id, chip_id, qid)` - Unique compound index
- `(project_id, username)` - Filter by project/member

```python
class CouplingDocument(Document):
    project_id: str
    username: str
    qid: str               # Coupling ID (e.g., "0-1")
    status: str = "pending"
    chip_id: str
    data: dict
    note: NoteModel = NoteModel()                  # Free-form per-coupling note
    metric_notes: dict[str, NoteModel] = {}        # Legacy global per-metric notes
    system_info: SystemInfoModel
```

**Note Fields:**

- `note` - Legacy global free-form note about the coupling. Scoped dashboard pinned summaries are stored in `TargetNoteDocument` when `PUT /chips/{chip}/couplings/{coupling_id}/note` includes `cooldown_id` or a time range.
- `metric_notes[metric_key]` - Legacy global per-metric annotations. Existing scoped per-metric notes are stored in `MetricNoteDocument`; new dashboard notes should use pinned summaries or forum discussions.

---

### MetricNoteDocument

**Collection:** `metric_note`

Stores the current dashboard metric note for one qubit/coupling metric in one operational scope. This collection supports both teams that manage explicit cool-down IDs and teams that only work from time ranges.

**Indexes:**

- `(project_id, chip_id, target_type, target_id, metric_key, scope_key)` - Unique current note per target metric and scope
- `(project_id, chip_id, scope_key, target_type, target_id)` - Dashboard notes summary
- `(project_id, chip_id, scope_started_at, scope_ended_at)` - Time-range fallback when cool-down docs are added later

```python
class MetricNoteDocument(Document):
    project_id: str
    chip_id: str
    target_type: str                 # "qubit" | "coupling"
    target_id: str                   # qid or coupling id
    metric_key: str
    note: NoteModel

    scope_type: str                  # "cooldown" | "time_range" | "global"
    scope_key: str                   # "cooldown:<id>", "time_range:<start>:<end>", or "global"
    cooldown_id: str | None
    scope_started_at: datetime | None
    scope_ended_at: datetime | None
    scope_source: str                # explicit_cooldown, current_cooldown, inferred_from_range, manual_time_range, legacy_global
    system_info: SystemInfoModel
```

When a cool-down ID is known, the note stores both `cooldown_id` and the cool-down time bounds. When no cool-down document exists, the dashboard can save a `time_range` note. If a cool-down document is added later, summary reads include matching time-range notes inside that cool-down until they are edited into the explicit cool-down scope.

---

### ChipNoteDocument

**Collection:** `chip_note`

Stores the current dashboard chip note in one operational scope. This is the writable dashboard chip-note store; the legacy global note remains on `ChipDocument.note`.

**Indexes:**

- `(project_id, chip_id, scope_key)` - Unique current chip note per scope
- `(project_id, chip_id, scope_started_at, scope_ended_at)` - Time-range fallback when cool-down docs are added later

```python
class ChipNoteDocument(Document):
    project_id: str
    chip_id: str
    note: NoteModel

    scope_type: str                  # "cooldown" | "time_range" | "global"
    scope_key: str                   # "cooldown:<id>", "time_range:<start>:<end>", or "global"
    cooldown_id: str | None
    scope_started_at: datetime | None
    scope_ended_at: datetime | None
    scope_source: str
    system_info: SystemInfoModel
```

When the dashboard has a selected cool-down, chip notes are stored under `scope_key = "cooldown:<id>"`, so each cool-down can carry a different chip-level summary.

### TargetNoteDocument

**Collection:** `target_note`

Stores the current dashboard pinned summary for one qubit/coupling target in one operational scope. This is the writable dashboard summary-note store; legacy global notes remain on `QubitDocument.note` and `CouplingDocument.note`.

**Indexes:**

- `(project_id, chip_id, target_type, target_id, scope_key)` - Unique current summary per target and scope
- `(project_id, chip_id, scope_key, target_type, target_id)` - Dashboard notes summary
- `(project_id, chip_id, scope_started_at, scope_ended_at)` - Time-range fallback when cool-down docs are added later

```python
class TargetNoteDocument(Document):
    project_id: str
    chip_id: str
    target_type: str                 # "qubit" | "coupling"
    target_id: str                   # qid or coupling id
    note: NoteModel

    scope_type: str                  # "cooldown" | "time_range" | "global"
    scope_key: str                   # "cooldown:<id>", "time_range:<start>:<end>", or "global"
    cooldown_id: str | None
    scope_started_at: datetime | None
    scope_ended_at: datetime | None
    scope_source: str
    system_info: SystemInfoModel
```

For `time_range` summary reads, notes are matched by **window overlap** rather than by an exact `scope_key`. The dashboard's default range is relative to "now", so its bounds drift by seconds/minutes between writing a note and reading it back; matching any `time_range` note whose `[scope_started_at, scope_ended_at]` window overlaps the requested window keeps those notes visible (issue #1109). When several overlapping notes exist for the same target metric, the one whose `scope_key` matches the request exactly wins, otherwise the most recently edited note is shown.

---

### ExecutionHistoryDocument

**Collection:** `execution_history`

Stores execution metadata only. Task results and calibration data are stored in separate collections
to support 256+ qubit systems (avoiding MongoDB's 16MB document limit).

**Indexes:**

- `(project_id, execution_id)` - Unique compound index
- `(project_id, chip_id, start_at)` - Supports metrics/best queries
- `(project_id, chip_id)` - Chip-based filtering
- `(project_id, username, start_at)` - Audit per user

```python
class ExecutionHistoryDocument(Document):
    project_id: str
    username: str
    name: str
    execution_id: str
    calib_data_path: str
    note: dict
    status: str
    tags: list[str]
    chip_id: str
    start_at: datetime
    end_at: datetime
    elapsed_time: float      # Stored in seconds
    message: str
    system_info: SystemInfoModel
```

**Related Collections:**

- Task results → `task_result_history` (query by `execution_id`)
- Calibration data → `qubit` / `coupling` collections

**Key Methods:**

- `from_execution_model(execution_model)` - Create from ExecutionModel
- `upsert_document(execution_model)` - Upsert operation

---

### TaskResultHistoryDocument

**Collection:** `task_result_history`

Primary storage for task execution results. Linked to executions via `execution_id`.

**Indexes:**

- `(project_id, task_id)` - Unique compound index
- `(project_id, execution_id)` - Join with execution_history
- `(project_id, chip_id, start_at)` - Time-based queries
- `(project_id, chip_id, name, qid, start_at)` - Latest task result queries
- `(project_id, chip_id, user_note.updated_at)` - **Partial sparse**: only docs with a user note. Powers `chip_notes_summary` without scanning the entire collection.

```python
class TaskResultHistoryDocument(Document):
    project_id: str
    username: str
    task_id: str
    name: str
    upstream_id: str
    status: str
    message: str
    input_parameters: dict
    output_parameters: dict
    output_parameter_names: list[str]
    note: dict                              # Internal calibration metadata (workflow)
    user_note: NoteModel = NoteModel()      # Dashboard-facing free-form note
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

**Note Fields:**

- `note` (existing) - Workflow internal calibration metadata (`dict`). Used by orchestrator / qubex backend.
- `user_note` (NEW) - Dashboard free-form note attached to this measurement. Edited via `PUT /task-results/{task_id}/note`. Indexed via partial sparse index for cheap chip-wide listing.

---

### QubitHistoryDocument

**Collection:** `qubit_history`

**Indexes:**

- `(project_id, chip_id, qid, recorded_date)` - Unique compound index

Daily snapshot history table.

```python
class QubitHistoryDocument(Document):
    project_id: str
    username: str
    qid: str
    status: str
    chip_id: str
    data: dict
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

### ChipHistoryDocument

**Collection:** `chip_history`

**Indexes:**

- `(project_id, chip_id, recorded_date)` - Unique compound index

```python
class ChipHistoryDocument(Document):
    project_id: str
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

- `(project_id, chip_id, qid, recorded_date)` - Unique compound index

```python
class CouplingHistoryDocument(Document):
    project_id: str
    username: str
    qid: str
    status: str
    chip_id: str
    data: dict
    system_info: SystemInfoModel
    recorded_date: str  # YYYYMMDD format
```

---

### TaskDocument

**Collection:** `task`

**Indexes:**

- `(project_id, name)` - Unique compound index
- `(project_id, task_type)` - Filter by scope

Stores task definition information.

```python
class TaskDocument(Document):
    project_id: str
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

- `(project_id, name)` - Unique compound index

```python
class BackendDocument(Document):
    project_id: str
    username: str
    name: str
    system_info: SystemInfoModel
```

---

### UserDocument

**Collection:** `user`

**Indexes:**

- `username` - Unique index
- `user_id` - Unique immutable internal identifier
- `access_token` - Unique index

```python
class UserDocument(Document):
    user_id: str
    username: str
    hashed_password: str
    access_token: str
    default_project_id: str | None = None
    full_name: str | None = None
    disabled: bool = False
    system_info: SystemInfoModel
```

---

### TagDocument

**Collection:** `tag`

**Indexes:**

- `(project_id, name)` - Unique compound index

```python
class TagDocument(Document):
    project_id: str
    username: str
    name: str
```

---

### ExecutionLockDocument

**Collection:** `execution_lock`

**Indexes:**

- `project_id` - Ensures one lock document per project

Singleton document for exclusive execution control. Ensures only one calibration runs at a time.

```python
class ExecutionLockDocument(Document):
    project_id: str
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

- `(project_id, date, chip_id)` - Unique compound index

Manages execution ID sequence numbers per date/user/chip.

```python
class ExecutionCounterDocument(Document):
    date: str           # YYYYMMDD format
    project_id: str
    username: str
    chip_id: str
    index: int          # Sequence number (starts from 0)
    system_info: SystemInfoModel
```

**Key Methods:**

- `get_next_index(project_id, date, chip_id)` - Atomically get next index

Generated execution ID format: `YYYYMMDD-NNN` (e.g., `20240101-001`)

---

### CalibrationNoteDocument

**Collection:** `calibration_note`

**Indexes:**

- `(project_id, execution_id, task_id, chip_id)` - Unique compound index
- `(project_id, chip_id, timestamp)` - Search index

```python
class CalibrationNoteDocument(Document):
    project_id: str
    username: str
    chip_id: str
    execution_id: str
    task_id: str
    note: dict
    timestamp: str  # ISO8601
    system_info: SystemInfoModel
```

---

### NoteEventDocument

**Collection:** `note_event`

Append-only audit log. The `NoteService` writes one row here on every
upsert/delete of a note (qubit, qubit metric, coupling, coupling metric, task
result). Used for: edit history, per-target timeline, full-text search across
all notes (knowledge view, LLM context).

**Indexes:**

- `(project_id, chip_id, created_at DESC)` - Chip-scoped chronological feed.
- `(project_id, scope, target_id, created_at DESC)` - Per-target timeline.
- `text(content)` - Full-text search across note contents within a project.

```python
class NoteEventDocument(Document):
    project_id: str
    chip_id: str
    scope: str           # qubit | qubit_metric | coupling | coupling_metric | task_result
    target_id: str       # qid for qubit/qubit_metric, coupling_id, or task_id
    metric_key: str = "" # only set for *_metric scopes
    action: str          # upsert | delete
    actor: str           # username
    content: str = ""    # Note content at time of action ("" for delete)
    extra: dict[str, str] = {}  # e.g. {"qid": "5", "task_name": "T1"}
    created_at: datetime
```

The collection is **never updated in place** — every entry is a new
immutable event. Two read patterns are exposed:

- `GET /chips/{chip_id}/note-events` (chip timeline)
- `GET /note-events/by-target?scope=&target_id=` (per-target timeline)
- `GET /note-events/search?q=` (cross-chip text search)

---

### CryostatDocument

**Collection:** `cryostat`

A long-lived piece of lab hardware (dilution refrigerator). Cool-downs reference this entity via ``cryo_id``.

**Indexes:**

- `(project_id, cryo_id)` - Unique compound index

```python
class CryostatDocument(Document):
    project_id: str
    cryo_id: str                 # Project-unique (e.g. "K-101")
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    location: str = ""
    status: str = "active"       # active | maintenance | decommissioned
    commissioned_at: datetime | None = None
    decommissioned_at: datetime | None = None
    note: NoteModel              # Free-form note (shared NoteModel)
    system_info: SystemInfoModel
```

CRUD endpoints under `/cryostats`. The `/cryo` UI page manages these.

---

### CooldownDocument

**Collection:** `cooldown`

One cool-down / warm-up cycle of one cryostat. The cool-down's `cooldown_id` is denormalized onto every task result, qubit history, and coupling history written while the chip is loaded into the cool-down — see [history denormalization](#history-denormalization-of-cooldown_id) below.

**Indexes:**

- `(project_id, cooldown_id)` - Unique compound index
- `(project_id, cryo_id, started_at DESC)` - Cool-downs by cryostat (newest first)
- `(project_id, chip_ids, started_at DESC)` - Cool-downs containing a chip
- `(project_id, started_at DESC)` - Project-wide chronological list

```python
class CooldownDocument(Document):
    project_id: str
    cooldown_id: str             # Project-unique (e.g. "2026-001")
    cryo_id: str                 # Owning cryostat
    description: str = ""
    started_at: datetime
    ended_at: datetime | None = None  # None = ongoing
    chip_ids: list[str] = []     # Chips loaded into this cool-down
    note: NoteModel
    system_info: SystemInfoModel
```

CRUD endpoints under `/cooldowns`. Chip assignment via:

- `POST /cooldowns/{cooldown_id}/chips/{chip_id}` — assign (also sets `chip.current_cooldown_id` if the cool-down is active)
- `DELETE /cooldowns/{cooldown_id}/chips/{chip_id}` — unassign (also clears `chip.current_cooldown_id` if it pointed here)

#### History denormalization of `cooldown_id`

When the workflow persists calibration data, the chip's `current_cooldown_id` is copied at write time onto:

- `TaskResultHistoryDocument.cooldown_id`
- `QubitHistoryDocument.cooldown_id`
- `CouplingHistoryDocument.cooldown_id`

This lets dashboards and metrics queries filter "show me only data from cool-down 2026-001" with a direct indexed lookup, instead of joining on time ranges.

A partial sparse index `(project_id, cooldown_id, start_at DESC)` on `task_result_history` ensures that cool-down filters scan only annotated rows.

---

### FlowDocument

**Collection:** `flows`

**Indexes:**

- `(project_id, name)` - Unique per project
- `(project_id, created_at)` - For sorted listing

Stores metadata for user-defined Python flows (custom calibration workflows).

```python
class FlowDocument(Document):
    name: str              # Flow name
    project_id: str
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

### SlackForumThreadDocument

Tracks the Slack message posted for each root forum thread, enabling reply and status-change notifications to appear in the same Slack thread.

Collection: `slack_forum_thread`

```python
class SlackForumThreadDocument(Document):
    post_id: str          # Forum root post ObjectId (unique)
    project_id: str
    channel_id: str       # Slack channel where the message was posted
    message_ts: str       # Slack message timestamp (used as thread_ts for replies)
    system_info: SystemInfoModel
```

---

## Entity Relationship Diagram (Conceptual)

![Database ER Diagram](../diagrams/database-er.drawio.png)

Other project-scoped collections (tasks, tags, backends, flows, counters, locks, histories) all reference `project_id`, ensuring a single sharing boundary per project.

---

## Data Flow

### During Calibration Execution

0. Resolve `(project_id, user_id)` via **ProjectMembershipDocument** and ensure the role includes write permission
1. Acquire per-project lock via **ExecutionLockDocument(project_id)**
2. Generate execution ID from **ExecutionCounterDocument** (YYYYMMDD-NNN scoped by project/chip)
3. Execute each task:
   - Save task results to **TaskResultHistoryDocument** (with `execution_id` for linking)
   - Update calibration data in **QubitDocument** / **CouplingDocument**
   - Save history to **QubitHistoryDocument** / **CouplingHistoryDocument**
4. Save execution metadata to **ExecutionHistoryDocument** (status, timing, notes only)
5. Save chip snapshot to **ChipHistoryDocument**
6. Release **ExecutionLock**

### During Cancellation

When a user cancels a running execution via the UI:

1. UI sends `POST /executions/{flow_run_id}/cancel` with the Prefect flow run UUID
2. API sets the Prefect flow run to `Cancelling` state via the Prefect client
3. Prefect sends SIGTERM to the worker process running the flow
4. Prefect triggers the `on_cancellation` hook registered on the `@flow` decorator
5. The hook reads `flow_run_id` from the execution's `note` field to locate the execution
6. All non-terminal tasks (running/scheduled/pending) are set to `cancelled`
7. The execution status is set to `cancelled`
8. The **ExecutionLock** is released

> **Note**: The `flow_run_id` (Prefect UUID) is stored in `ExecutionHistoryDocument.note["flow_run_id"]`
> at the start of each flow run. This bridges the QDash execution ID (`YYYYMMDD-NNN`) with
> the Prefect flow run UUID, enabling the cancel operation.

### Data Architecture (256+ Qubit Support)

To avoid MongoDB's 16MB document limit with large qubit counts:

```
┌─────────────────────────┐
│  ExecutionHistoryDoc    │  ← Metadata only (~2KB)
│  - execution_id         │
│  - status, timing       │
│  - tags, note           │
└───────────┬─────────────┘
            │ execution_id
            ▼
┌─────────────────────────┐
│  TaskResultHistoryDoc   │  ← Individual task results
│  - task_id              │     (one doc per task)
│  - execution_id (FK)    │
│  - output_parameters    │
└─────────────────────────┘

┌─────────────────────────┐
│  QubitDocument          │  ← Calibration data
│  CouplingDocument       │     (persistent storage)
└─────────────────────────┘
```

---

## Datetime

Persisted timestamps are managed in **UTC**. Client display converts API UTC
timestamps to the configured timezone, currently Asia/Tokyo.

- `created_at`, `updated_at`: ISO8601 format
- `recorded_date`: YYYYMMDD format in the configured calendar timezone
- `calibrated_at`: ISO8601 format
