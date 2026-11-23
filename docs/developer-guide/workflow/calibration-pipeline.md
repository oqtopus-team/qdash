# Calibration Pipeline Spec

A version 2 pipeline spec selects targets and ordered task calls without Python source.

```json
{
  "spec_version": 2,
  "name": "coherence",
  "targets": {"qids": ["0"]},
  "steps": [{
    "type": "CustomOneQubit",
    "step_name": "coherence",
    "tasks": [{"name": "CheckT1", "update_calibration_parameters": false}]
  }]
}
```

The selected chip must already have the task's required calibration. Specs cannot reference code.
Calls use the same settings and identity rules as [Python task calls](./task-calls.md).

## Endpoints

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /calibration-pipelines/catalog` | Read | Supported steps, tasks, modes, and spec schema |
| `POST /calibration-pipelines/validate` | Read | Problems, warnings, and resolved plan |
| `POST /calibration-pipelines/execute` | Edit | Validate and dispatch to the system worker |

Validation returns `valid: false` with paths into the spec. Execute rejects invalid specs with
422 and missing worker registration with 503. The plan digest links validation, execution notes,
and task invocations.

Execute records intent before launch and joins the supplied calibration session or creates an
automatic one. Reusing `idempotency_key` replays the recorded request; omitting it starts new work.
For unknown dispatch outcomes and audit fields, see
[Calibration Sessions](../agent/calibration-sessions.md).

### Version 1 specs

Missing `spec_version` means version 1. The API rejects it with a deterministic `migrated_spec`:
names become calls, repeated calls/steps receive unique IDs, and old run defaults become
deprecated per-task defaults. The worker converts version 1 specs queued before upgrade.
Old `mode` keys and execution-mode names must be corrected separately; they are not auto-migrated.
Other versions are rejected.

### Preflight checks

Validation checks task availability and type, settings, topology, step references, and manual
rounds before dispatch. It also checks required qubit inputs and readout-duration compatibility,
allowing for earlier calls that publish required outputs. Overrides do not satisfy a missing
required database input. Coupling-input completeness is not checked by this preflight.
Unavailable task catalogs or unsupported Qubex topology fail validation rather than bypassing it.

## Steps

| Kind | Types |
| --- | --- |
| Configuration | `ConfigureAll` |
| One-qubit calibration | `BringUp`, `OneQubitCheck`, `OneQubitFineTune`, `CustomOneQubit` |
| Filtering | `FilterByStatus`, `FilterByMetric` |
| Two-qubit scheduling | `GenerateCRSchedule` |
| Two-qubit calibration | `TwoQubitCalibration`, `CustomTwoQubit` |

Use the catalog for current default tasks and dependencies. Calibration steps need unique IDs;
custom steps use `step_name`. `ConfigureAll.call` sets its task settings, while target-derived
MUX IDs take priority. Top-level `task_parameters` remains accepted with a deprecation warning;
[migrate settings to calls](./task-calls.md#migrate-per-task-defaults).

### Execution Modes

One-qubit steps use `parallel_by_round` by default, or `parallel_by_mux`, `sequential`,
`simultaneous_spectroscopy`, or `manual`. Two-qubit steps use `automatic` or `manual`.
Manual mode requires rounds; rounds without manual mode and manual two-qubit parallelism caps
are invalid. See the [scheduler](../architecture/one-qubit-scheduler.md#manual-rounds).

### Filters

Filters reference an earlier step and optionally one call. A failed or missing referenced call
removes the target; no earlier success substitutes for it. Custom-step metric filters require a
call ID. Without a step reference, filters read the latest check or fine-tune step.

## Following a run

Each calibration step creates an execution; transforms do not. Execution details expose the
whole `pipeline`, including step status and figures. Use that aggregate rather than treating
completion of the first step as completion of the run. Client wait helpers do this by default.

## Where the pieces live

- `src/qdash/datamodel/calibration_pipeline.py`: schema, catalog, migration, validation
- `src/qdash/datamodel/task_call.py`: shared calls
- `src/qdash/workflow/service/pipeline_flow.py`: worker flow

Test API validation and workflow execution with `task test-api` and `task test-workflow`.
