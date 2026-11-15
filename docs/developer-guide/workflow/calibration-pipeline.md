# Calibration Pipeline Spec

A calibration pipeline spec describes targets and ordered task calls as JSON. Agents and clients
can run it without writing Python; each step maps to the same Step class used by flow templates.

```json
{
  "spec_version": 2,
  "name": "coarse-then-two-pass-ramsey",
  "targets": { "qids": ["0", "1"] },
  "steps": [
    { "type": "OneQubitCheck", "execution_mode": "parallel_by_mux" },
    { "type": "FilterByStatus" },
    {
      "type": "CustomOneQubit",
      "step_name": "coherence",
      "continue_on_failure": true,
      "tasks": [
        { "name": "CheckT1" },
        {
          "name": "CheckRamsey",
          "call_id": "ramsey_coarse",
          "run": { "detuning": 0.001, "shots": 1024 }
        },
        {
          "name": "CheckRamsey",
          "call_id": "ramsey_fine",
          "run": { "detuning": 0.0002, "shots": 1024 }
        }
      ]
    },
    {
      "type": "FilterByMetric",
      "step": "coherence",
      "call_id": "ramsey_fine",
      "metric": "t2_star",
      "threshold": 10.0
    }
  ],
  "default_run_parameters": { "interval": 153600 }
}
```

Each `tasks` entry is a [TaskCall](./task-calls.md), with the same normalization and validation
as Python flows. Repeated tasks need distinct `call_id` values. `default_run_parameters` supplies
shared run values.

The deprecated top-level `task_parameters` supplies per-task defaults below each call's settings.
It remains supported for saved and queued specs, but validation reports a warning.
[Migrate these defaults onto calls](./task-calls.md#migrate-per-task-defaults).

The spec cannot reference code. Each `type` maps to one Step class, task names must be enabled for the backend and match the step's task type, and anything else is rejected before dispatch.

## Endpoints

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| `GET /calibration-pipelines/catalog` | viewer | Step types with their dependencies, default calls, default step id, and step-level metrics; the backend's tasks by type; the accepted `spec_version`; and the JSON schema of the spec |
| `POST /calibration-pipelines/validate` | viewer | Dry run: every problem with a path into the spec, warnings, and the resolved steps with each call's id, failure policy, and effective settings |
| `POST /calibration-pipelines/execute` | editor | Validate, then run the spec as one execution through the worker's `system-calibration-pipeline` deployment |

For a bad spec, `validate` returns `valid: false` and path-specific `problems`, such as
`targets.qids[1]: qubit '99' is not on chip 64Qv3`, rather than HTTP 422. Warnings identify
allowed but suspect choices, including deprecated `task_parameters`; they do not invalidate a spec.

The response includes `plan_digest`, stored as `note.pipeline.spec_digest` by each step execution.
Task results store the worker-resolved plan digest in `invocation.plan_digest`, matching
`note.calibration_plan.digest`. `execute` returns HTTP 422 with the validation problems, or 503
when the worker deployment is not registered.

### Version 1 specs

A missing `spec_version` means version 1. The API rejects version 1 with a problem at
`spec_version` and a deterministic `migrated_spec`:

- Task names become calls; repeated names get `<Task>`, `<Task>_2`, and subsequent unused IDs.
- Repeated built-in steps get `<name>_2` and subsequent unused step IDs.
- `task_run_parameters` becomes deprecated `task_parameters.<task>.run`, which produces a warning.
- Filters without `step` still read the latest `OneQubitFineTune` or `OneQubitCheck`.

`migrate_pipeline_spec` does not migrate execution modes. A one-qubit step using `mode` or
`serial`, `scheduled`, or `synchronized` raises `LegacyExecutionModeError`. Validation reports
the required replacement at each `steps[i]` and returns no migrated spec until the owner fixes
those fields. Other spec versions are rejected without conversion.

The worker converts and logs version 1 specs queued before the upgrade. A queued spec with an
obsolete mode fails before execution with the same migration message.

### Preflight checks

Beyond the spec's shape, `validate` reports what a task would reject before it measures anything, so a run does not fail at step 1 with empty results. The checks read the task metadata the API already has (`TaskInfo`: declared inputs, run parameters, and outputs), the target qubits' calibration data, and the run parameters recorded on the task that produced a persisted parameter. They do not import workflow code.

| Check | Problem path | What it catches |
| --- | --- | --- |
| Run parameter names | `task_parameters.<task>.run.<name>`, `steps[i].tasks[j].run.<name>`, `steps[i].call.run.<name>` | A name the task does not declare, or a calibration input set under `run` |
| Input names | `task_parameters.<task>.input.<name>`, `steps[i].tasks[j].input.<name>`, `steps[i].call.input.<name>` | A name the task does not declare, or a run parameter set under `input` |
| Run parameter types | `task_parameters.<task>.run.<name>`, `steps[i].tasks[j].run.<name>`, `steps[i].call.run.<name>`, `default_run_parameters.<name>` | A value whose type the declaration cannot take, such as a sweep for `shots`; a shared value is checked against every pipeline task that declares it, and one that no task declares is reported because it would be ignored |
| Session readout duration | `default_run_parameters.readout_duration`, `task_parameters.<task>.run.readout_duration`, `steps[i].tasks[j].run.readout_duration` | A non-positive shared value, or a per-task or per-call value that differs from the session (`readout_duration` is session-scoped in Qubex; the session uses the shared value, or 1024 ns when none is set) |
| Batch inputs | `steps[i].tasks[j]` or `steps[i]` | A `simultaneous_spectroscopy` step whose calls set calibration inputs, which batch execution does not support |
| Required inputs | `steps[i].tasks[j]` | A `database_required` input of a qubit task that no earlier call in the pipeline publishes and that a target qubit lacks in its calibration data, such as `CheckT1` without Rabi parameters. A call publishes its outputs unless its effective `update_calibration_parameters` (the call's own value, else `task_parameters.<task>`) is `false`. An `input` override does not satisfy the requirement, because the task loads required inputs from the database before it applies overrides |
| Rabi readout duration | `steps[i].tasks[j]` | Rabi parameters a task restores that were measured under a different readout duration than this pipeline's session, when no earlier `CheckRabi` call in the pipeline publishes new ones |

Coupling steps are not checked for required inputs; their inputs span two qubits and a coupling. For `mux_ids` targets the checks cover the MUX's topology members minus `exclude_qids`. A `qids` target must be defined by the chip topology; a standalone qubit (in no MUX) is valid, but `BringUp` and a `ConfigureAll` without `mux_ids` reject it. With either target form, each explicit `ConfigureAll` `mux_ids` entry must be a MUX of the chip topology and is reported at `steps[i].mux_ids[j]` otherwise; at run time, the session and the Qubex `ConfigureAll` task refuse an undefined MUX ID before any box is configured. An empty or omitted `mux_ids` keeps the task's default selection and reserves the whole chip. When the backend's task catalog cannot be read, the spec is reported invalid at `backend_name` rather than passed unchecked. On the Qubex backend, a chip topology whose MUX layout Qubex cannot drive, including any standalone qubit, is also reported at `backend_name` (see [Qubex Backend Restriction](../architecture/square-lattice-topology.md#qubex-backend-restriction)).

## Steps

| Type | Kind | Runs | Needs before it |
| --- | --- | --- | --- |
| `ConfigureAll` | calibration | one `ConfigureAll` call, or `call`, for `mux_ids` or the targets' MUXes | nothing |
| `BringUp` | calibration | `BRINGUP_TASKS` or `tasks` | nothing |
| `OneQubitCheck` | calibration | `CHECK_1Q_TASKS` or `tasks` | nothing |
| `OneQubitFineTune` | calibration | `FULL_1Q_TASKS_AFTER_CHECK` or `tasks` | nothing |
| `CustomOneQubit` | calibration | `tasks` (qubit tasks) | nothing |
| `FilterByStatus` | transform | keeps qubits whose referenced step or call succeeded | the referenced step, else `OneQubitCheck` or `OneQubitFineTune` |
| `FilterByMetric` | transform | keeps qubits with `metric >= threshold` in the referenced step or call | the referenced step, else `OneQubitCheck` or `OneQubitFineTune` |
| `GenerateCRSchedule` | transform | plans parallel CR groups | candidate qubits |
| `TwoQubitCalibration` | calibration | `FULL_2Q_TASKS` or `tasks` | candidate qubits |
| `CustomTwoQubit` | calibration | `tasks` (coupling tasks) | candidate qubits |

### Execution Modes

One-qubit steps support `parallel_by_round` (default), `parallel_by_mux`, `sequential`, and
`simultaneous_spectroscopy`; see [Execution Modes](../architecture/one-qubit-scheduler.md#execution-modes).
Removed names and the `mode` key fail at `steps[i]`; use the
[migration map](../architecture/one-qubit-scheduler.md#migrate-from-the-former-names).

One-qubit calibration steps also accept `manual` with `rounds`. Two-qubit steps accept
`automatic` (default) or `manual` with `[control, target]` rounds. Validation rejects rounds
without manual mode, manual mode without rounds, and an explicit `max_parallel_ops` on a manual
two-qubit step. It checks rounds against the chip and, before filters run, the candidates. See
[Manual Rounds](../architecture/one-qubit-scheduler.md#manual-rounds).

The catalog exposes `one_qubit_execution_modes` and `two_qubit_execution_modes`. Default fields
are omitted from dumps to preserve existing plan digests.

### Step Identity and Configuration

Every calibration step needs a unique `step_id`: a custom step uses `step_name`; a built-in
step uses its explicit `step_id` or catalog name. Custom steps also accept `continue_on_failure`.

`configure: true` on `OneQubitCheck` or `OneQubitFineTune` prepends a `Configure` call with that
call ID. An explicit Configure call or a colliding ID makes the step invalid.

`ConfigureAll` accepts an optional `call` naming that task, for example
`{"name": "ConfigureAll", "run": {"configuration_mode": "ge-ef-cr"}}`. It replaces the
`task_parameters.ConfigureAll` entry; without it, the call has no settings of its own. The
step's `mux_ids`, or the target MUXes, override `run.mux_ids` and produce a validation warning
when replacing a supplied value. Targets use either `qids` or `mux_ids` with optional `exclude_qids`.

### Filters

A filter with `step` reads that earlier step, and with `call_id` one of its calls; a failed or missing call removes the qubit without falling back to another call of the same task. A metric filter on a step without `call_id` reads the step-level metrics the catalog lists for it; custom steps have none. A filter without `step` reads the latest `OneQubitFineTune` or `OneQubitCheck`, as in version 1. [Task Calls](./task-calls.md#results) describes the selection in full.

The step order is checked the same way `Pipeline._validate` checks it in the worker: a step that lists several requirements needs at least one of them, and a filter that references a step needs that step, with that call, earlier in the pipeline.

## Following a run

`CalibService.run` gives every calibration step its own execution; transform steps create none. The executions of one run share `note.flow_run_id`, carry `note.step_index`, `note.step_id`, and `note.calibration_plan` with the resolved calls and its digest, and, for a spec run, `note.pipeline` with the planned steps, `spec_version`, and `spec_digest`. Every task result carries `invocation` with its `step_id` and `call_id`, so `GET /task-results?execution_id=...&call_id=ramsey_fine` returns one call's results. `GET /executions/{id}` on any of them returns a `pipeline` field that covers the whole run: the plan with each step's execution id, status (`pending`, `skipped` for transforms, or the execution's own), task counts, and the figures of its finished tasks. `pipeline.status` is `running` while any step runs or the run still holds the project lock between steps, and otherwise the outcome of the last step.

Readers that want the whole run use that field rather than the first execution's status, which completes when step 1 does. `QDashClient.waitForExecution` does so by default (`wholePipeline: false` waits for the single execution), so pi-qdash's `qdash_wait_execution` returns when the run ends, and the chat's execution card shows every step and figure as the run advances.

## Where the pieces live

| File | Role |
| --- | --- |
| `src/qdash/datamodel/calibration_pipeline.py` | The spec models, the step catalog (`STEP_CATALOG`), the default call lists, the step-order and reference checks, and `migrate_pipeline_spec`. Free of workflow imports so the API can validate without a Prefect runtime |
| `src/qdash/datamodel/task_call.py` | `TaskCall`, `TaskSettings`, and call id rules, shared with Python flows |
| `src/qdash/workflow/service/pipeline_flow.py` | The `calibration-pipeline` system flow: converts a queued version 1 spec, builds Step and Target objects, checks the context, and runs them like `CalibService.run` with the request's backend and the spec's per-task defaults |
| `src/qdash/workflow/register_system_flows.py` | Registers `system-calibration-pipeline` on worker startup |
| `src/qdash/api/services/calibration_pipeline_service.py` | Version handling, chip, backend, and task-type checks, resolved calls, warnings; the catalog |
| `src/qdash/api/services/calibration_pipeline_preflight.py` | The preflight checks: run and input names and types, batch inputs, the session readout duration, required inputs, and the Rabi readout duration |
| `src/qdash/api/services/flow_service/` | `execute_calibration_pipeline` in `service.py`; lock claim, Prefect run and execution row in `execution.py` |
| `src/qdash/api/routers/calibration_pipeline.py` | The three endpoints |

`STEP_CATALOG` restates each Step class's `requires` and `provides`; `tests/qdash/workflow/service/test_pipeline_flow.py` asserts the two agree, so adding a Step means adding a spec model, a catalog entry, a `build_step` branch, and an entry in that test's `EVERY_STEP` list. The same test checks that the API resolves the same calls as the Step objects run. The default call lists live in the datamodel module for the same reason; `qdash.workflow.service.tasks` re-exports them.

## Agent use

The Copilot agent composes a spec from the catalog and the flow templates, validates it, and shows the resolved steps, with each call's id, in an approval card before `execute` runs. The spec is the only thing the agent writes; the procedure it encodes still comes from the templates and Step classes, and the deterministic gates in the engine judge every task result as they do for a saved flow.
