# Calibration Pipeline Spec

A calibration pipeline spec is a JSON description of a calibration run: the spec version, the targets, an ordered list of steps with their task calls, and the settings of those calls. It lets an agent or a client start a calibration without writing a Python flow, while the steps it can use are exactly the Step classes the templates are built from.

```json
{
  "spec_version": 2,
  "name": "coarse-then-two-pass-ramsey",
  "targets": { "qids": ["0", "1"] },
  "steps": [
    { "type": "OneQubitCheck", "mode": "scheduled" },
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

Each entry in `tasks` is a [task call](./task-calls.md): `name`, an optional `call_id`, `run`, `input`, `update_calibration_parameters`, and `on_failure`. The same task may run several times in one step when every occurrence has its own `call_id`. `default_run_parameters` holds run values shared by every task that declares them. The top-level `task_parameters`, per-task defaults keyed by task name that every call of the task starts from, is deprecated: the schema marks it `deprecated`, `validate` reports a warning at `task_parameters`, and QDash still applies it under each call's own values, so saved and queued specs run unchanged. Move its values onto the calls as [Task Calls](./task-calls.md#migrate-per-task-defaults) describes. The models are shared with Python flows, so the spec and a flow normalize and validate calls identically.

The spec cannot reference code. Each `type` maps to one Step class, task names must be enabled for the backend and match the step's task type, and anything else is rejected before dispatch.

## Endpoints

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| `GET /calibration-pipelines/catalog` | viewer | Step types with their dependencies, default calls, default step id, and step-level metrics; the backend's tasks by type; the accepted `spec_version`; and the JSON schema of the spec |
| `POST /calibration-pipelines/validate` | viewer | Dry run: every problem with a path into the spec, warnings, and the resolved steps with each call's id, failure policy, and effective settings |
| `POST /calibration-pipelines/execute` | editor | Validate, then run the spec as one execution through the worker's `system-calibration-pipeline` deployment |

`validate` never fails with a 422 for a bad spec. It returns `valid: false` and a `problems` list such as `targets.qids[1]: qubit '99' is not on chip 64Qv3`, so a caller can correct the spec. `valid` is true exactly when `problems` is empty; `warnings` point at allowed but probably unintended choices, such as a filter without `step` placed after a custom step it will not read, or deprecated ones such as a non-empty `task_parameters`, and never make a spec invalid. The response also carries `plan_digest`, the digest of the validated spec, which each step execution stores as `note.pipeline.spec_digest`; task results carry the digest of the plan the worker resolved (`note.calibration_plan.digest`) in `invocation.plan_digest`. `execute` returns the same problems in the 422 detail when the spec is not valid, and 503 when the worker has not registered the deployment yet.

### Version 1 specs

A version 1 spec (no `spec_version`, or `spec_version: 1`) is rejected with one problem at `spec_version` and a `migrated_spec` that runs the same tasks with the same settings: every task name becomes a call, a name listed more than once in one step gets `call_id` values `<Task>`, `<Task>_2`, and so on, skipping ids the step already uses, a built-in step repeated in the pipeline gets `step_id` values `<name>_2`, `<name>_3`, and so on, skipping ids a custom step already uses, and `task_run_parameters` moves to `task_parameters.<task>.run`, so the migrated spec can carry the deprecated `task_parameters` and its validation reports the warning. Filters without `step` keep reading the latest `OneQubitFineTune` or `OneQubitCheck`, so the new step ids do not change what they read. `migrate_pipeline_spec` performs the conversion; it is pure and deterministic. Any other `spec_version` is rejected with a problem at `spec_version` and no `migrated_spec`. The worker applies the same conversion only to a version 1 spec that was queued before the upgrade, and logs it.

### Preflight checks

Beyond the spec's shape, `validate` reports what a task would reject before it measures anything, so a run does not fail at step 1 with empty results. The checks read the task metadata the API already has (`TaskInfo`: declared inputs, run parameters, and outputs), the target qubits' calibration data, and the run parameters recorded on the task that produced a persisted parameter. They do not import workflow code.

| Check | Problem path | What it catches |
| --- | --- | --- |
| Run parameter names | `task_parameters.<task>.run.<name>`, `steps[i].tasks[j].run.<name>` | A name the task does not declare, or a calibration input set under `run` |
| Input names | `task_parameters.<task>.input.<name>`, `steps[i].tasks[j].input.<name>` | A name the task does not declare, or a run parameter set under `input` |
| Run parameter types | `task_parameters.<task>.run.<name>`, `steps[i].tasks[j].run.<name>`, `default_run_parameters.<name>` | A value whose type the declaration cannot take, such as a sweep for `shots`; a shared value is checked against every pipeline task that declares it, and one that no task declares is reported because it would be ignored |
| Session readout duration | `default_run_parameters.readout_duration`, `task_parameters.<task>.run.readout_duration`, `steps[i].tasks[j].run.readout_duration` | A non-positive shared value, or a per-task or per-call value that differs from the session (`readout_duration` is session-scoped in Qubex; the session uses the shared value, or 1024 ns when none is set) |
| Batch inputs | `steps[i].tasks[j]` or `steps[i]` | A `simultaneous_spectroscopy` step whose calls set calibration inputs, which batch execution does not support |
| Required inputs | `steps[i].tasks[j]` | A `database_required` input of a qubit task that no earlier call in the pipeline publishes and that a target qubit lacks in its calibration data, such as `CheckT1` without Rabi parameters. A call publishes its outputs unless its effective `update_calibration_parameters` (the call's own value, else `task_parameters.<task>`) is `false`. An `input` override does not satisfy the requirement, because the task loads required inputs from the database before it applies overrides |
| Rabi readout duration | `steps[i].tasks[j]` | Rabi parameters a task restores that were measured under a different readout duration than this pipeline's session, when no earlier `CheckRabi` call in the pipeline publishes new ones |

Coupling steps are not checked for required inputs; their inputs span two qubits and a coupling. For `mux_ids` targets the checks cover the MUX's four qubits minus `exclude_qids`. When the backend's task catalog cannot be read, the spec is reported invalid at `backend_name` rather than passed unchecked.

## Steps

| Type | Kind | Runs | Needs before it |
| --- | --- | --- | --- |
| `ConfigureAll` | calibration | ConfigureAll for the targets' MUXes | nothing |
| `BringUp` | calibration | `BRINGUP_TASKS` or `tasks` | nothing |
| `OneQubitCheck` | calibration | `CHECK_1Q_TASKS` or `tasks` | nothing |
| `OneQubitFineTune` | calibration | `FULL_1Q_TASKS_AFTER_CHECK` or `tasks` | nothing |
| `CustomOneQubit` | calibration | `tasks` (qubit tasks) | nothing |
| `FilterByStatus` | transform | keeps qubits whose referenced step or call succeeded | the referenced step, else `OneQubitCheck` or `OneQubitFineTune` |
| `FilterByMetric` | transform | keeps qubits with `metric >= threshold` in the referenced step or call | the referenced step, else `OneQubitCheck` or `OneQubitFineTune` |
| `GenerateCRSchedule` | transform | plans parallel CR groups | candidate qubits |
| `TwoQubitCalibration` | calibration | `FULL_2Q_TASKS` or `tasks` | candidate qubits |
| `CustomTwoQubit` | calibration | `tasks` (coupling tasks) | candidate qubits |

One-qubit steps take `mode` (`synchronized`, `scheduled`, `simultaneous_spectroscopy`, `serial`). Custom steps take a `step_name` and `continue_on_failure`. Every calibration step has a `step_id`: a custom step's `step_name`, a built-in step's `step_id` field, or the catalog name (`one_qubit_check`); it must be unique within the pipeline, so a spec that runs `OneQubitCheck` twice sets `step_id` on at least one of them. `configure: true` on `OneQubitCheck` or `OneQubitFineTune` runs a `Configure` call with `call_id` `Configure` before the step's calls; a step that sets it and also lists a `Configure` call, or another call with that `call_id`, is invalid at `steps[i]`. Targets are either `qids` or `mux_ids` with optional `exclude_qids`.

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
| `src/qdash/workflow/service/pipeline_flow.py` | The `calibration-pipeline` system flow: converts a queued version 1 spec, builds Step and Target objects, and calls `CalibService.run` |
| `src/qdash/workflow/register_system_flows.py` | Registers `system-calibration-pipeline` on worker startup |
| `src/qdash/api/services/calibration_pipeline_service.py` | Version handling, chip, backend, and task-type checks, resolved calls, warnings; the catalog |
| `src/qdash/api/services/calibration_pipeline_preflight.py` | The preflight checks: run and input names and types, batch inputs, the session readout duration, required inputs, and the Rabi readout duration |
| `src/qdash/api/services/flow_service/` | `execute_calibration_pipeline` in `service.py`; lock claim, Prefect run and execution row in `execution.py` |
| `src/qdash/api/routers/calibration_pipeline.py` | The three endpoints |

`STEP_CATALOG` restates each Step class's `requires` and `provides`; `tests/qdash/workflow/service/test_pipeline_flow.py` asserts the two agree, so adding a Step means adding a spec model, a catalog entry, a `build_step` branch, and an entry in that test's `EVERY_STEP` list. The same test checks that the API resolves the same calls as the Step objects run. The default call lists live in the datamodel module for the same reason; `qdash.workflow.service.tasks` re-exports them.

## Agent use

The Copilot agent composes a spec from the catalog and the flow templates, validates it, and shows the resolved steps, with each call's id, in an approval card before `execute` runs. The spec is the only thing the agent writes; the procedure it encodes still comes from the templates and Step classes, and the deterministic gates in the engine judge every task result as they do for a saved flow.
