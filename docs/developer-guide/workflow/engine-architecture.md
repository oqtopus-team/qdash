# Workflow Engine Architecture

The workflow engine turns a calibration task name and target into a tracked hardware operation.
It owns task execution and persistence; Prefect-facing session composition belongs to the service
layer described in [Workflow Services](./services.md).

## Responsibility Boundaries

| Component | Responsibility | Does not own |
| --- | --- | --- |
| `CalibService` | The author contract: checked context, run metadata, and `run(targets, steps)` | Lifecycle, reservations, or workers |
| `CalibSession` | Pipeline and Execution lifecycle, hardware reservation, worker settings, and terminal cleanup | Task internals or project authorization |
| `CalibOrchestrator` | One execution's backend, task context, and execution record | Cross-step scheduling or resource reservation |
| `ExecutionService` | Execution state transitions and repository persistence | Task-result state |
| `TaskContext` | In-memory task state, artifacts, and the configured `TaskExecutor` | Execution-level status |
| `TaskExecutor` | Preprocess, run, postprocess, validation, and result persistence | Prefect flow structure |
| Backend | Hardware-specific operations and calibration-note updates | QDash lifecycle policy |

`CalibService` is the entry point for flow authors; see
[Workflow Author Contract](./services.md#workflow-author-contract). It builds one typed
`SessionSettings` and hands it to an internal `CalibSession`, which owns everything below. Direct
use of `CalibOrchestrator` is useful in engine tests and low-level integrations, but callers then
own initialization and terminal handling themselves.

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
    participant Service as CalibSession
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
    Service->>Service: finish, fail, or cancel, then release reservation
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
  state. The orchestrator passes it the call's resolved `update_calibration_parameters`; when
  that is `False`, the task is recorded without promoting its outputs. For QM tasks, which run
  on the `qm` and `qm-fake` backends, it promotes outputs only when the backend reports
  `is_hardware`, before `force_update_params` is considered, so a QOP simulator or `qm-fake` run
  cannot replace a measured value; those outputs stay in the task result with
  `database_updated` set to `False`.
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

`CalibSession` resolves qubit or MUX inputs into an `ExecutionResourceScope` before hardware work.
A pipeline reserves the union of all step scopes before its first step and retains the same owner
until the pipeline reaches a terminal path. The single-task executor reserves its one target the
same way. Isolated workers borrow the owner's Execution and reservation; they never acquire or
release the reservation.

Repository implementations compare the requested chip, resource keys, and `exclusive` flag
atomically. A task whose requested scope exceeds the pipeline reservation is rejected before the
backend call.

## Isolated Workers

`SessionSettings` in `service/_internal/settings.py` is the one record of how a run measures and
publishes. Every session of a run is built from it: the owner session of each pipeline step, the
single-task executor's session, and every isolated worker. `CalibSession.worker_spec()` is the
only place that derives worker settings, as a frozen, picklable `WorkerSpec` that Prefect and
Dask pass to worker processes; `borrowed_session()` opens the worker and releases only its
backend when the block ends.

| Setting | Worker policy |
| --- | --- |
| Context, backend, run metadata, `default_run_parameters`, per-task defaults | Inherited unchanged |
| Configuration mode | Inherited as resolved by the owner, including the layout a `ConfigureAll` step selected |
| Snapshot source (`source_execution_id`, `source_task_id`, exempt tasks) | Inherited, so a re-execution restores the same snapshot in every worker |
| `force_update_params` | Inherited |
| GitHub pull and push | Disabled; the owner pulls before and pushes after its Execution |
| Execution and reservation | Borrowed through `WorkerLease`; never claimed, created, finished, locked, or unlocked |

Serial and batch strategies run in the owner's session, which an in-process Prefect task reads
through `session_context.get_session()`.

## Cancellation

Cancellation has two paths because a running worker can observe either a Prefect cancellation
exception or a process termination signal.

- A `CancelledRun` or `CancelledError` raised inside an Execution that a session owns cancels it
  through `CalibSession.owned_execution()`, which also completes it on success and fails it on
  any other exception.
- A Prefect-installed termination signal leaves the execution open. The registered
  `on_flow_cancellation` or `on_flow_crashed` hook finds executions by `flow_run_id`, assigns the
  correct terminal status, finalizes unfinished tasks, and releases the reservation.

Top-level flows that own a reservation, including `single-task-executor`, use the ordinary terminal
hooks. The `*_keep_lock` variants are for nested flows that borrow another run's reservation. If
`project_id` was resolved from the user's default project, terminal hooks recover it from the
execution history recorded for the same `flow_run_id`. Initialization also releases its
reservation on signals or cancellation before the run holds an Execution. The helpers in
`service/_internal/lifecycle.py` implement the exception classification and terminal hooks, and
`service/calib_service.py` re-exports the hooks for flows; flow templates should not reproduce
that policy independently.

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

### Keep the fake backend in step with qubex

The fake backend runs the qubex task classes against `FakeExperiment`
(`engine/backend/fake_qubex/simulation.py`), a QUBEX-compatible simulator. Its task set is the
`fake` section of `config/app/backend.yaml`: `calibtasks/fake/__init__.py` routes every listed
name that the fake package does not implement to the qubex class of the same name, and
`scripts/generate_task_catalog.py` publishes the qubex declarations under the fake backend. The
only fake-only task is `FakeBringUp`, which seeds a fresh project with the simulator's device
parameters in place of the hardware bring-up tasks. `BackendSaver` persists fake outputs through
the same path as qubex outputs, so a routed task finds what the task before it published.

To add a qubex task to the fake backend, list it in `backend.yaml` and run the fake template; a
gap in the simulator shows up as an `AttributeError` on `FakeExperiment`, which is fixed in
`simulation.py`, never by a fake copy of the task. Keep the fix at the measurement level: the
simulator answers `sweep_parameter`, `repeat_sequence` and the coherence experiments with
physically shaped IQ data, and qubex's own analysis and figures (for example the chevron matched
transform in `qubex.contrib`) run on top of it unchanged. An emulator-side re-implementation of a
qubex analysis is drift waiting to happen and is removed when found. `tests/qdash/workflow/calibtasks/
test_fake_backend_sync.py` fails when the list names a task qubex no longer has, when a fake
class shadows a qubex task, or when the template's default chain can no longer resolve a
required input from the tasks before it.

### Add a QM task to the qm-fake backend

The `qm-fake` backend (`QMFakeBackend` in `engine/backend/qm_fake.py`) plays the role for `qm`
that the `fake` backend plays for qubex: the task runs its real experiment code and only the
device is replaced. `QMFakeBackend.get_instance()` returns a `QMFakeSession` whose `manager` is a
`QMFakeQuantumMachinesManager` (`engine/backend/qm_fake_qop.py`) instead of a
`qm.QuantumMachinesManager`. `run_rabi` in `calibtasks/qm/rabi_experiment.py` is the one code
path for both: it builds the `QUA_calibrations` Rabi, opens a quantum machine with the QUA
configuration, lets `run_calibrations` generate and execute the program, then fetches the `I`
and `Q` handles and converts them with `demod2volts`. The fake path differs only in labelling:
`mode="fake"`, its raw data source type, and the device's execution report in the metadata.
The backend therefore needs the workflow `qm` extra; without it `connect` raises
`QMDependencyError` and nothing falls back to another response.

The fake device implements only the SDK calls that path makes, with signatures that are
subsets of the SDK's: `open_qm(config)` validates the configuration with the SDK's
`qm.program.load_config` for the capabilities of `qop_version`, `execute(program)` accepts a
`qm.Program`, and the job's `result_handles` offers `wait_for_all_values()` and
`get(name).fetch_all()`. `execute` decodes `program.qua_program` and interprets a fixed QUA
subset: scalar variables, `for_` loops evaluated in QUA fixed-point and int arithmetic,
`play(op * amp(a))` on a bound drive element, `measure` with `demod.full` or `dual_demod.full` on
a bound readout element, `align`, `wait`, `save`, and the stream operators `buffer`, `average`
and `save`. Any other statement, operator, or protobuf field raises `QMFakeUnsupportedError`,
so a newer SDK that emits a different program fails instead of producing data. The model is
described in the module docstring of `qm_fake_qop.py`; it checks no compilation, timing,
waveform output or wiring.

The task set is the `qm-fake` section of `config/app/backend.yaml`: `calibtasks/qm/__init__.py`
routes every listed name to the `qm` class of the same name, and
`scripts/generate_task_catalog.py` publishes the `qm` declaration under `qm-fake`. The task class
keeps `backend = "qm"`, which names the task family; `BaseBackend.name` (`qm` or `qm-fake`)
names the backend a run used. To offer a new QM task on `qm-fake`, keep the task on the shared
SDK path, extend the interpreter and the model to the statements its program uses with tests in
`calibtasks/qm/test_qm_fake_device.py`, and list the task under `qm-fake`. A task whose program
the fake device cannot run stays off the list. `calibtasks/qm/test_qm_fake.py` fails when the
list names a task the `qm` backend does not define.

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
| Author contract | `service/calib_service.py`, `service/context.py` | `tests/qdash/workflow/service/test_calib_service.py`, `test_calib_context.py` |
| Lifecycle, reservations, and worker settings | `service/_internal/session.py`, `_internal/settings.py`, `_internal/lifecycle.py` | `tests/qdash/workflow/service/test_calib_session.py` |
| Scheduling | `engine/scheduler/` | `tests/qdash/workflow/engine/scheduler/` |

Run `task test-workflow` after engine changes. Also run the repository or API test suites when a
change crosses those boundaries.
