# Workflow Engine Architecture

The engine executes and records tasks; the service layer owns pipelines and reservations.

## Responsibility Boundaries

| Component | Owns |
| --- | --- |
| `CalibService` | Checked author context and `run(targets, steps)` |
| `CalibSession` | Pipeline lifecycle, reservations, and workers |
| `CalibOrchestrator` | One execution's backend and context |
| `ExecutionService` | Execution state and persistence |
| `TaskContext` | In-memory task state and artifacts |
| `TaskExecutor` | Task lifecycle and result persistence |
| Backend | Hardware-specific operations |

## Execution Identity

Execution IDs are project-wide daily sequences, allocated atomically by
`src/qdash/dbmodel/project_execution_counter.py`. Initial allocation starts beyond retained
legacy IDs. Deploy API allocators and workers together with ID creation paused: old chip-local
allocators cannot safely coexist. Existing collisions are not repaired automatically.

## Task Lifecycle

The executor resolves inputs, validates them, preprocesses, runs hardware, saves raw data,
postprocesses, validates outputs, and records results. Batch execution invokes one experiment
and distributes its results to target records. See [Parameter Resolution](./parameter-resolution.md).

## State and Persistence

Execution and task states have separate managers. `ExecutionService.merge_calib_data()` changes
memory only; repositories own durable calibration. `TaskHistoryRecorder` saves history,
`BackendSaver` publishes accepted outputs, and the filesystem saver writes scoped artifacts.
See [Calibration Data Lifecycle](./calibration-data-lifecycle.md).

## Hardware Reservations

A session reserves the union of pipeline scopes before hardware work and retains it until a
terminal path. Requests exceeding that scope fail before the backend call. Worker sessions
borrow the owner execution and reservation; only the owner can release them.

## Isolated Workers

`SessionSettings` is the run's configuration. `worker_spec()` produces frozen worker settings:
context, parameters, snapshot policy, configuration mode, and pinned MUX mapping are inherited;
GitHub pull/push is disabled. Workers never reread topology during a run.
MUX tasks require a valid pinned mapping and fail before measuring when it is unavailable.

## Cancellation

Owned executions close on success, failure, or cancellation exceptions. For termination signals,
Prefect terminal hooks find executions by flow-run ID, finalize unfinished tasks, and release
reservations. Top-level flows use normal hooks; nested borrowers use `*_keep_lock` hooks.
Reuse this policy instead of duplicating it in templates.

## Add a calibration task

Implement a task under `src/qdash/workflow/calibtasks/`, register it in the backend configuration,
and test input resolution, validation, persistence, and failure handling. Keep hardware calls
in the run phase and publication policy in the engine.

## Document a calibration task

Declare `TaskDocumentation` with a required `description` and optional `when_to_use` and
`prerequisites`. Use literal keyword values; the API parses source without importing it.
Prerequisites explain expected state but do not enforce it: `input_spec` does.
Run `task generate-task-catalog` after editing declarations. Static parsing and catalog coverage
are tested in `tests/qdash/api/services/test_task_file_service.py` and
`tests/scripts/test_generate_task_catalog.py`.

## Add a backend

Implement `BaseBackend` and construction in `engine/backend/factory.py`. Test connection and
supported operations rather than adding backend-name branches throughout the engine.

## Keep the fake backend in step with qubex

The fake backend runs Qubex task classes against `FakeExperiment`; only `FakeBringUp` is
fake-only. Add supported tasks in `config/app/backend.yaml` and implement missing measurements
in `engine/backend/fake_qubex/simulation.py`, reusing Qubex analysis.
Fake fault injection is opt-in, scoped, and expires; its rules are covered by
`tests/qdash/workflow/engine/backend/test_fake_faults.py`.

## Source and Tests

Runtime code lives under `src/qdash/workflow/engine/`; session policy is under
`src/qdash/workflow/service/_internal/`. Tests mirror these boundaries under
`tests/qdash/workflow/`. Run `task test-workflow` and, for shared persistence or HTTP changes,
the corresponding repository or API tests. Scheduling is covered by the
[1-qubit](../architecture/one-qubit-scheduler.md) and [CR](../architecture/cr-scheduler.md) guides.
