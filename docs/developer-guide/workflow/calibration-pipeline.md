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

The spec's `name` is optional and separate from the calibration session's name. When supplied,
it prefixes each step's execution name as `<name>_<step name>`; when omitted, the execution
uses the step name alone. The execution list appends the execution ID to this name.
Tags combine the spec's tags and the execute request's tags; `pipeline` is not added automatically.

## Endpoints

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /calibration-pipelines/catalog` | Read | Supported steps, tasks, modes, and spec schema |
| `POST /calibration-pipelines/validate` | Read | Problems, warnings, and resolved plan |
| `POST /calibration-pipelines/execute` | Edit | Validate and dispatch to the system worker |
| `POST /calibration-pipelines/plans` | Edit | Validate and save an immutable proposal |
| `GET /calibration-pipelines/plans/{plan_id}` | Edit, creator | Read the stored preview, including its expiry status |
| `POST /calibration-pipelines/plans/{plan_id}/execute` | Edit, creator | Recheck and dispatch the approved proposal |

Validation returns `valid: false` with paths into the spec. Execute rejects invalid specs with
422 and missing worker registration with 503. Validation's `plan_digest` identifies the spec;
task invocations carry a separate worker-resolved plan digest.

Execute records intent before launch and joins the supplied calibration session or creates an
automatic one. Reusing `idempotency_key` replays the recorded request; omitting it starts new work.
For unknown dispatch outcomes and audit fields, see
[Calibration Sessions](../agent/calibration-sessions.md).

## Stored plans

Plan creation requires `chip_id`, `spec`, and an `idempotency_key`; `backend_name` is optional.
It validates and saves at most 256 KiB of submitted spec without creating a run, session, or
hardware reservation. It materializes and validates default task lists, so it can reject a spec
that `/validate` accepts with omitted tasks. On topology-backed chips, selected MUXes with
non-excluded qubits need wiring; missing wiring returns 422. Plan creation and fresh execution
also reject expanded MUX qubits without a record on the chip. Add the missing record or list
that member in `targets.exclude_qids`; an excluded member does not need a database record.
The preview includes
resolved calls, initial MUX-expanded qubits, defaults, warnings, and a versioned SHA-256
`review_digest`. This differs from the spec's `plan_digest` and the worker's invocation digest.

Plans belong to their creator in one project and expire after 24 hours. GET can display an
expired plan; new execution and creation-key replay return 410 after expiry. A new plan needs a
new creation key and ID. Repeating an unexpired creation request with the same key returns the
same plan; changing its payload returns 409. TTL cleanup removes plans seven days after expiry.
Creation-key deduplication lasts only while the plan is stored. After cleanup, reusing a key
can create a new ID; it never revives the old approval.

Reference execution requires `chip_id` and `expected_review_digest` from the reviewed plan.
The API revalidates the stored definition and compares its resolved content before dispatch.
It refuses changed content with 409 and invalid inputs with 422. For the new plan endpoints,
422 responses carry `detail` as a body-validation error list, an object with `message` and
`problems`, or a domain-error string; clients must handle all three shapes. The worker compares the
approved content against its actual steps, expanded initial targets, and run settings before
resource acquisition. Filters still select later targets from measured results. Calibration
values, scientific defaults inside task code, task code, and hardware state are not frozen.

Use matching API and worker releases for this contract. Restart the upgraded worker so it
registers a deployment whose `approved_plan` parameter advertises
`x-qdash-approved-plan-contract: 1`. Missing or incompatible schemas return 503 before a new run
is admitted; QDash checks again immediately before dispatch. Existing spec execution remains
available. This checks the registered contract, not the code actually running on a worker;
do not leave old workers serving the same deployment.

Execution idempotency is separate from creation idempotency. Reuse the launch key to recover the
same recorded request: an already dispatched run can replay even after plan cleanup. An unknown
dispatch outcome requires reconciliation, not a new launch key. Each new execution still needs
its own authority. SDK calls do not provide the interactive approval of Agent or pi CLI.
Run records retain `plan_id`, `review_digest`, and `approved_plan` for audit after plan deletion.
Calibration session reads of a run (`GET /calibration-sessions/{calibration_session_id}` and its
`runs/{run_id}`) return `plan_id` and `review_digest`, which are null for a run started from a spec.
See [Code Mode and approval](../agent/calibration-design.md#preserve-the-proposal-through-approval-and-execution).

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
custom steps use `step_name`. `ConfigureAll` uses step-level `mux_ids` when set, otherwise
target-derived MUX IDs; either overrides `call.run.mux_ids`. Other task settings come from `call`.
Top-level `task_parameters` remains accepted with a deprecation warning;
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

Every reached step creates an execution, including filters and schedule generation. Execution
details expose the whole `pipeline`, with `key` identifying each step occurrence and `transform`
carrying a transform's recorded outcome. Measurements retain task counts and figures. Use the
aggregate rather than treating completion of the first step as completion of the run.

`pending` means the run may still reach the step; `skipped` means it ended without reaching it.
`not_recorded` identifies transforms in old runs that did not record them. It does not imply
success or failure. Transform execution status comes from its own record, not from an empty
task list. Existing history is not backfilled.

## Where the pieces live

- `src/qdash/datamodel/calibration_pipeline.py`: schema, catalog, migration, validation
- `src/qdash/datamodel/task_call.py`: shared calls
- `src/qdash/workflow/service/pipeline_flow.py`: worker flow

Test API validation and workflow execution with `task test-api` and `task test-workflow`.
