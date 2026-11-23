# Workflow Services

Workflow services save project flows, register Prefect deployments, and connect runs to QDash history.

## Responsibility Boundaries

| Component | Owns |
| --- | --- |
| API `FlowService` | Flow files, metadata, and dispatch admission |
| API `FlowScheduleService` | Project-scoped schedules |
| Deployment service | Source import and Prefect registration |
| Prefect server and worker | Queuing and running entrypoints |
| `CalibService` | Checked author contract |
| `CalibSession` | Runtime lifecycle and reservations |

## Workflow Author Contract

`CalibService` accepts the user/chip/project context, run metadata, and shared run defaults.
Targets and steps go to `run()`; settings go to `TaskCall`. QDash owns execution IDs, reservations,
workers, and cleanup. No finish call is needed.

`resolve_calib_context()` checks an enabled user and active project write permission. Direct
Python callers use `CalibService.from_context()`. Workers recheck permissions, so a schedule
cannot retain access its creator has lost.

| Removed argument | Replacement |
| --- | --- |
| `qids`, `muxes` | Targets passed to `run()` |
| `task_parameters`, `task_run_parameters` | Settings on each `TaskCall` |
| `name` | `flow_name` |
| `backend_name` | Checked context with `backend=` |
| `configuration_mode` | First `ConfigureAll` call's run settings |
| Execution, lock, repository, and GitHub controls | Runtime-owned policy; remove from author code |
| Snapshot controls | Single-task re-execution or a `source_execution_id` flow parameter |

### Configuration mode and GitHub policy

A first `ConfigureAll` step can set the layout for the pipeline and its workers. Otherwise initial
layout follows runtime settings and `QUBEX_CONFIGURATION_MODE`.
GitHub synchronization follows `config/app/workflow.yaml` and only applies to Qubex. Credentials
alone do not enable it. Measurement-only calls do not disable step-level pull/push.
Internal callers needing different policy use checked context and `SessionSettings` through
`service/_internal/runs.py`; workers never pull or push.

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
- `src/qdash/workflow/service/calib_service.py` and `context.py`: author contract
- `src/qdash/workflow/service/_internal/`: runtime policy

Run `task test-api` for persistence/dispatch changes and `task test-workflow` for runtime changes;
run both when a change crosses that boundary.
