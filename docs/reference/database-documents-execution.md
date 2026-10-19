# Execution Documents

Documents written while a calibration runs: execution metadata, per-task results, AI evaluations of those results, the execution lock and counter, workflow-internal notes, and user-defined flows.

Collections overview: [Database Structure](./database-structure.md).

## ExecutionHistoryDocument

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

**Note fields used by the runtime:**

| Key | Written by | Purpose |
|-----|-----------|---------|
| `flow_run_id` | API on trigger, `CalibService._initialize()` on creation | Links the record to its Prefect flow run (cancel, terminal hooks, reconciliation) |
| `claimed_at` | `MongoExecutionRepository.claim_scheduled_execution()` | Marks a pre-created `scheduled` record as adopted by a flow process |

**Related Collections:**

- Task results → `task_result_history` (query by `execution_id`)
- Calibration data → `qubit` / `coupling` collections

**Key Methods:**

- `from_execution_model(execution_model)` - Create from ExecutionModel
- `upsert_document(execution_model)` - Upsert operation

---

## TaskResultHistoryDocument

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

## EvaluationRunDocument

**Collection:** `evaluation_run`

One bulk calibration evaluation request: the latest result of one task for every qubit or coupling of a chip (or one day's results), judged by the evaluation model through the Pi Agent Runtime without a planner. Runs are the unit of comparison between extension versions, models and task references.

**Indexes:**

- `(run_id)` - Unique
- `(project_id, chip_id, requested_at)` - Runs of a chip, newest first

```python
class EvaluationRunDocument(Document):
    run_id: str                       # evr_<hex>
    project_id: str
    chip_id: str
    task_name: str
    entity_type: str                  # "qubit" | "coupling"
    date: str | None                  # YYYYMMDD for a historical day, None for latest
    question: str | None
    trigger: str                      # "bulk" (chip page) | "single" (one task result) | "chat" (planner)
    mode: str                         # "direct" | "planner"
    planner_model: str | None         # provider/modelId of the planner, in planner mode
    requested_by: str
    requested_at: datetime
    completed_at: datetime | None
    status: str                       # "running" | "completed"
    total: int
    completed_count: int
    failed_count: int
    model: str | None                 # provider/modelId of the first evaluation
    evaluator: EvaluatorModel | None  # extension name, version, source, commit
```

---

## EvaluationDocument

**Collection:** `evaluation`

One `qcal_evaluate` call for one task result, stored as the runtime reported it so the record stands on its own after the extension, model or task knowledge changes: what the model saw (evidence context, exact prompt, reference size and hash, figure hashes), what it answered (diagnosis or raw text, model, duration, usage), which extension judged, and the human verdict added afterwards.

**Indexes:**

- `(evaluation_id)` - Unique
- `(run_id, qid)` - Records of one run
- `(project_id, task_id, requested_at)` - Evaluations of one task result across runs

```python
class EvaluationDocument(Document):
    evaluation_id: str                # ev_<hex>
    run_id: str
    project_id: str
    chip_id: str
    task_id: str
    task_name: str
    qid: str
    execution_id: str
    status: str                       # "pending" | "running" | "completed" | "failed"
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    input: EvaluationInputModel | None    # context, prompt, question, knowledge_chars/sha256, figures[]
    output: EvaluationOutputModel | None  # model, fallback, diagnosis, raw, parsed, duration_ms, usage
    evaluator: EvaluatorModel | None
    planner: EvaluationPlannerModel | None  # model, answer, tool_calls, duration_ms (planner mode)
    verdict: EvaluationVerdictModel | None  # agree, note, username, updated_at
```

---

## ExecutionLockDocument

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

## ExecutionCounterDocument

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

## CalibrationNoteDocument

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

## FlowDocument

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
