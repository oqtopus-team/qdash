# Workflow Engine Architecture

The workflow engine turns a calibration task name and target into a tracked hardware operation.
It owns task execution and persistence; Prefect-facing session composition belongs to the service
layer described in [Workflow Services](./services.md).

## Responsibility Boundaries

| Component | Responsibility | Does not own |
| --- | --- | --- |
| `CalibService` | Pipeline lifecycle, hardware reservation, Prefect terminal hooks, and high-level steps | Task internals |
| `CalibOrchestrator` | One execution's backend, task context, and execution record | Cross-step scheduling or resource reservation |
| `ExecutionService` | Execution state transitions and repository persistence | Task-result state |
| `TaskContext` | In-memory task state, artifacts, and the configured `TaskExecutor` | Execution-level status |
| `TaskExecutor` | Preprocess, run, postprocess, validation, and result persistence | Prefect flow structure |
| Backend | Hardware-specific operations and calibration-note updates | QDash lifecycle policy |

`CalibService` is the normal entry point for flow authors. Direct use of
`CalibOrchestrator` is useful in engine tests and low-level integrations, but callers then own
initialization and terminal handling themselves.

## Execution Identity

Execution IDs use a daily sequence shared by every chip and user in a project.
For example, allocations for two chips can produce `20261027-000` and
`20261027-001`. Different projects and dates have independent sequences. This matches
the `(project_id, execution_id)` identity used by execution history and task queries.

`ProjectExecutionCounterDocument` in `src/qdash/dbmodel/project_execution_counter.py`
allocates numbers atomically in `project_execution_counter`. On the first allocation
for a project and date, it starts above the largest retained legacy counter or numeric
execution ID in execution and task history. The legacy `execution_counter` collection
remains available for chip date lookups; new counters track participating chips.

Deploy all API services and workflow workers that allocate IDs together, with ID
creation paused during the switch. Older processes still allocate chip-local IDs and
cannot safely run alongside the shared allocator. The switch preserves existing
records; it does not repair IDs that previously collided or reconstruct overwritten
execution history.

## Execution Path

```mermaid
sequenceDiagram
    participant Flow as Prefect flow
    participant Service as CalibService
    participant Orchestrator as CalibOrchestrator
    participant Runner as Prefect task wrapper
    participant Executor as TaskExecutor

    Flow->>Service: start pipeline
    Service->>Service: reserve complete hardware scope
    Service->>Orchestrator: initialize execution
    Orchestrator->>Orchestrator: create state, context, and backend
    Flow->>Service: run step
    Service->>Orchestrator: run_task or run_task_batch
    Orchestrator->>Runner: submit task
    Runner->>Executor: execute lifecycle
    Executor-->>Orchestrator: task state and calibration data
    Orchestrator-->>Service: task outputs
    Service->>Service: finish, fail, or cancel; release reservation
```

The Prefect wrappers in `engine/task_runner.py` are intentionally thin. They invoke the executor
and save `TaskContext`; task semantics remain testable without a running Prefect server.

## State and Persistence

QDash keeps execution state and task state separate.

- `ExecutionStateManager` holds the execution status, note, timing, and in-memory calibration
  data. `ExecutionService` persists state changes through `ExecutionRepository` and uses
  optimistic locking for concurrent note updates.
- `TaskStateManager` is the source of truth for per-target task status, parameters, messages,
  figures, and raw-data paths. Task results keep the raw output names; its in-memory `calib_data`
  is keyed by the published parameter names declared through `publish_targets`, so it mirrors the
  calibration database and the finish-time params YAML selection sees the same names.
- `TaskHistoryRecorder` writes task-result history and optional provenance records.
- `BackendSaver` decides which validated outputs update the backend and accepted calibration
  state. `persist_output_parameters=False` records the task without promoting its outputs.
- `FilesystemCalibDataSaver` writes artifacts beneath the execution's project- and chip-scoped
  calibration directory.

`ExecutionService.merge_calib_data()` updates only its in-memory model. Task and chip repositories
own durable calibration results; do not assume that saving an execution document persists its
`calib_data` field.

## Task Lifecycle

For a single target, `TaskExecutor.execute()` performs these phases:

1. Resolve database or snapshot inputs and apply user overrides.
2. Validate effective inputs and mark the task as running.
3. Run optional preprocessing, prepare the hardware call, and execute the task.
4. Save raw data before task-specific postprocessing.
5. Validate R² and fidelity and process output parameters.
6. Save figures, history, provenance, and permitted backend updates.
7. Mark the task completed or failed and return `TaskExecutionResult`.

<Diagram name="task-lifecycle" caption="Which component writes what during each TaskExecutor phase, and where it lands. Execution state is saved on a separate path." />

Batch execution follows the same policy through `execute_batch()`, but calls the task's
`batch_run()` once and then distributes results to individual target records. Use a batch task
only when one backend experiment genuinely covers all supplied qubits.

Parameter precedence and snapshot behavior are documented in
[Parameter Resolution](./parameter-resolution.md). The promotion of measured values into accepted
state is documented in [Calibration Data Lifecycle](./calibration-data-lifecycle.md).

## Hardware Reservations

`CalibService` resolves qubit or MUX inputs into an `ExecutionResourceScope` before hardware work.
A pipeline reserves the union of all step scopes before its first step and retains the same owner
until the pipeline reaches a terminal path. Child workers use `use_lock=False` and borrow the
parent execution; they must not acquire or release the parent's reservation.

Repository implementations compare the requested chip, resource keys, and `exclusive` flag
atomically. A task whose requested scope exceeds the pipeline reservation is rejected before the
backend call.

## Cancellation

Cancellation has two paths because a running worker can observe either a Prefect cancellation
exception or a process termination signal.

- A `CancelledRun` or `CancelledError` handled inside the flow calls
  `CalibService.cancel_calibration()`.
- A Prefect-installed termination signal leaves the execution open. The registered
  `on_flow_cancellation` or `on_flow_crashed` hook finds executions by `flow_run_id`, assigns the
  correct terminal status, finalizes unfinished tasks, and releases the reservation.

Top-level flows that own a reservation, including `single-task-executor`, use the ordinary terminal
hooks. The `*_keep_lock` variants are for nested flows configured with `use_lock=False` that borrow
the parent pipeline's reservation. If `project_id` was resolved inside `CalibService`, terminal hooks
recover it from the execution history recorded for the same `flow_run_id`. Initialization also
releases its reservation on signals or cancellation before the caller receives the session.
The shared flow helpers in `service/calib_service.py` implement the exception classification and
terminal behavior; flow templates should not reproduce that policy independently.

<Diagram name="execution-reservation" caption="The pipeline owner reserves hardware once; borrowers are checked against that reservation, and only the owner's terminal paths release it." />

## Extension Points

### Add a calibration task

Implement the task contract under `workflow/calibtasks/`, register the class in the backend's task
configuration, and test preprocessing, effective parameter resolution, result validation, and
failure behavior. Keep backend calls inside the task's run phase and persistence policy inside the
engine.

### Add a backend

Implement `BaseBackend`, add construction logic to `engine/backend/factory.py`, and provide tests
for connection lifecycle and the task operations it supports. Avoid branching on backend names in
the orchestrator or executor.

### Add persistence behavior

Depend on repository protocols and inject an in-memory implementation in tests. State-transition
rules belong in a state manager or service; database-specific query logic belongs in the repository
implementation.

### Change scheduling

Schedulers return execution groups but do not execute them. See the
[1-Qubit Scheduler](../architecture/one-qubit-scheduler.md),
[1-Qubit Ordering Strategies](../architecture/one-qubit-ordering-strategies.md), and
[CR Gate Scheduler](../architecture/cr-scheduler.md) before changing parallelism.

## Source and Tests

| Concern | Source | Focused tests |
| --- | --- | --- |
| Session composition | `engine/orchestrator.py` | `tests/qdash/workflow/engine/test_orchestrator_*.py` |
| Execution lifecycle | `engine/execution/` | `tests/qdash/workflow/engine/execution/` |
| Task lifecycle | `engine/task/` and `engine/task_runner.py` | `tests/qdash/workflow/engine/task/` |
| High-level lifecycle and reservations | `service/calib_service.py` | `tests/qdash/workflow/service/test_calib_service.py` |
| Scheduling | `engine/scheduler/` | `tests/qdash/workflow/engine/scheduler/` |

Run `task test-workflow` after engine changes. Also run the repository or API test suites when a
change crosses those boundaries.
