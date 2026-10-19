# Database Structure

QDash uses MongoDB via the Bunnet ODM with a project-centric multi-tenant model. The data model has two layers:

- **datamodel** (`src/qdash/datamodel/`) — Pydantic `BaseModel` for business logic; fields in [Data Models](./data-models.md)
- **dbmodel** (`src/qdash/dbmodel/`) — Bunnet `Document` for database persistence; fields per collection in [Calibration Documents](./database-documents-calibration.md), [Execution Documents](./database-documents-execution.md) and [Collaboration Documents](./database-documents-collaboration.md)

The [Calibration Data Lifecycle](../developer-guide/workflow/calibration-data-lifecycle.md) explains
which collections hold accepted values versus measurement history and how workflow outputs move
between MongoDB, active execution state, and Qubex parameter files.

## MongoDB Collections

Each document class links to the page that lists its fields, indexes and methods.

| Collection            | Document Class                                                                               | Description                                                |
| --------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `project`             | [ProjectDocument](./database-documents-collaboration.md#projectdocument)                     | Project metadata (owner-centric workspace)                 |
| `project_membership`  | [ProjectMembershipDocument](./database-documents-collaboration.md#projectmembershipdocument) | User membership & role per project                         |
| `chip`                | [ChipDocument](./database-documents-calibration.md#chipdocument)                             | Quantum chip configuration scoped to a project             |
| `qubit`               | [QubitDocument](./database-documents-calibration.md#qubitdocument)                           | Individual qubit data                                      |
| `coupling`            | [CouplingDocument](./database-documents-calibration.md#couplingdocument)                     | Qubit coupling information                                 |
| `execution_history`   | [ExecutionHistoryDocument](./database-documents-execution.md#executionhistorydocument)       | Calibration execution history                              |
| `task_result_history` | [TaskResultHistoryDocument](./database-documents-execution.md#taskresulthistorydocument)     | Task result history                                        |
| `qubit_history`       | [QubitHistoryDocument](./database-documents-calibration.md#qubithistorydocument)             | Daily qubit snapshots                                      |
| `chip_history`        | [ChipHistoryDocument](./database-documents-calibration.md#chiphistorydocument)               | Daily chip snapshots                                       |
| `coupling_history`    | [CouplingHistoryDocument](./database-documents-calibration.md#couplinghistorydocument)       | Daily coupling snapshots                                   |
| `task`                | [TaskDocument](./database-documents-calibration.md#taskdocument)                             | Task definitions                                           |
| `backend`             | [BackendDocument](./database-documents-calibration.md#backenddocument)                       | Backend configurations (project scoped)                    |
| `user`                | [UserDocument](./database-documents-collaboration.md#userdocument)                           | User authentication / default project bootstrap            |
| `tag`                 | [TagDocument](./database-documents-collaboration.md#tagdocument)                             | Project-level tag management                               |
| `execution_lock`      | [ExecutionLockDocument](./database-documents-execution.md#executionlockdocument)             | Exclusive execution lock                                   |
| `execution_counter`   | [ExecutionCounterDocument](./database-documents-execution.md#executioncounterdocument)       | Execution ID counter                                       |
| `calibration_note`    | [CalibrationNoteDocument](./database-documents-execution.md#calibrationnotedocument)         | Calibration notes (workflow internal)                      |
| `flows`               | [FlowDocument](./database-documents-execution.md#flowdocument)                               | User-defined flows                                         |
| `metric_note`         | [MetricNoteDocument](./database-documents-collaboration.md#metricnotedocument)               | Legacy dashboard metric notes scoped by cooldown/range     |
| `chip_note`           | [ChipNoteDocument](./database-documents-collaboration.md#chipnotedocument)                   | Dashboard chip notes scoped by cooldown/range              |
| `target_note`         | [TargetNoteDocument](./database-documents-collaboration.md#targetnotedocument)               | Dashboard pinned target summaries scoped by cooldown/range |
| `note_event`          | [NoteEventDocument](./database-documents-collaboration.md#noteeventdocument)                 | Audit log for every note edit (write-through)              |
| `forum_label`         | [ForumLabelDocument](./database-documents-collaboration.md#forumlabeldocument)               | Custom project-scoped forum labels                         |
| `slack_forum_thread`  | [SlackForumThreadDocument](./database-documents-collaboration.md#slackforumthreaddocument)   | Slack message posted for each root forum thread            |
| `cryostat`            | [CryostatDocument](./database-documents-calibration.md#cryostatdocument)                     | Cryostat (dilution refrigerator) entity                    |
| `cooldown`            | [CooldownDocument](./database-documents-calibration.md#cooldowndocument)                     | One cool-down cycle of one cryostat                        |
| `evaluation_run`      | [EvaluationRunDocument](./database-documents-execution.md#evaluationrundocument)             | One bulk calibration evaluation request                    |
| `evaluation`          | [EvaluationDocument](./database-documents-execution.md#evaluationdocument)                   | One `qcal_evaluate` snapshot and its human verdict         |

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
