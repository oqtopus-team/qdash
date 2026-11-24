# Workflow Services

Workflow services save project flows, register Prefect deployments, and connect runs to QDash history.

## Responsibility Boundaries

| Component | Owns |
| --- | --- |
| API `FlowService` | Flow files, metadata, and dispatch admission |
| API `FlowScheduleService` | Project-scoped schedules |
| Deployment service | Source import and Prefect registration |
| Prefect server and worker | Queuing and running entrypoints |
| `CalibrationSession` | Checked author context and grouped calibration execution |
| `ExecutionRuntime` | Runtime lifecycle and reservations |

## Workflow Author Contract

`CalibrationSession.from_context()` binds a checked user/chip/project context to the launch's
calibration work. Pass shared definitions from `qdash.calibration` to `run(targets, steps)`;
run metadata, tags, and `default_run_parameters` belong on that call. QDash owns execution IDs,
reservations, workers, and cleanup. The persistent group itself holds no hardware.

`resolve_calib_context()` checks an enabled user and active project write permission. Workers
recheck permissions, so a schedule cannot retain access its creator has lost.
`run()` returns `CalibrationResult` after its steps finish; execution errors propagate.
`validate()` checks definitions and dependency order without hardware or writes; unlike SDK
validation, it does not read chip state or preflight calibration data.

`@calibration_flow(session_name="...")` installs terminal hooks and declares the automatic
group's name. The API reads the literal before dispatch; the worker uses the same metadata for
scheduled/direct runs. An explicitly selected session keeps its name. Old `@flow` sources and
`CalibService` remain supported; see the [migration steps](./quickstart.md#preserve-terminal-handling).

### Configuration mode and GitHub policy

A first `ConfigureAll` step can set the layout for the pipeline and its workers. Otherwise initial
layout follows runtime settings and `QUBEX_CONFIGURATION_MODE`.
GitHub synchronization follows `config/app/workflow.yaml` and only applies to Qubex. Credentials
alone do not enable it. Measurement-only calls do not disable step-level pull/push.
Internal callers needing different policy use checked context and `SessionSettings` through
`service/_internal/runs.py`; workers never pull or push.

### Step History

Each reached step, including filters and schedule generation, gets an Execution in the launch's
run and session. Transform records contain their outcome without tasks or measurement artifacts.
Execution detail shows **Step outcome** for these records. A saved workflow with several
`run()` calls lists all executions; aggregate per-step progress is currently available only for
the system pipeline flow, whose source-independent plan has one step sequence.

## Save and Register a Flow

The API formats and validates source, writes the shared project file, asks the deployment service
to import/register it, then stores metadata. A create-only save returns 409 if the name exists;
per-flow file locking and unique metadata prevent concurrent overwrite.
Replacement preserves schedules and default parameters, but Prefect replacement is not
transactional. Send deployment changes through QDash to avoid racing direct Prefect edits.

## Dispatch a Run

The API merges saved and requested parameters, then injects authenticated user, project, and flow
identity. It reserves hardware before Prefect dispatch and records a scheduled execution.
Dispatch failures release the claim. Cron runs instead claim resources and allocate their
execution at worker start.

### Per-run Target Overrides

An override selects MUXes, qubits, or directed coupling pairs for this run only. The API reports
supported modes by inspecting source without executing it; the worker applies the same contract.
Manual rounds accept no override. Unsupported target classes and unknown steps fail rather than
running unchanged. Filters still narrow candidates, and separate nested flows keep their targets.

### Execution Plan Preview

Preview reads saved source and chip configuration without imports, writes, reservations, or
hardware access. Bounded static inspection returns no partial plan when source is unresolved.
Manual rounds expose validation issues; automatic groups form at runtime. Runtime revalidates.
QDash has 16 worker slots per group; external Prefect limits can reduce actual concurrency.

## Manage Schedules

A schedule uses either cron or one scheduled time. Cron lives on the deployment; one-time work
is a scheduled Prefect run. Resaving preserves schedules and parameters. External deployment
concurrency settings are not preserved by replacement.

## Resolve Files and Artifacts

`src/qdash/common/config/path_resolver.py` maps shared paths across API and worker environments.
Do not construct container paths in routers or templates. Calibration artifacts live beneath
`CALIB_DATA_PATH` with project/chip scope.

## Handle Terminal States

Owner hooks close interrupted records and release reservations; borrowers keep the owner's lock.
See [Cancellation](./engine-architecture.md#cancellation).

## Source and Tests

- `src/qdash/api/services/flow_service/`: files, dispatch, source inspection
- `src/qdash/api/services/flow_schedule_service.py`: schedules
- `src/qdash/workflow/deployment_service.py`: registration
- `src/qdash/workflow/service/calibration_session.py` and `context.py`: author contract
- `src/qdash/workflow/service/_internal/`: runtime policy

Run `task test-api` for persistence/dispatch changes and `task test-workflow` for runtime changes;
run both when a change crosses that boundary.
