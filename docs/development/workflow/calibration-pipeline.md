# Calibration Pipeline Spec

A calibration pipeline spec is a JSON description of a calibration run: the targets, an ordered list of steps, and run parameters. It lets an agent or a client start a calibration without writing a Python flow, while the steps it can use are exactly the Step classes the templates are built from.

```json
{
  "name": "coarse-then-coherence",
  "targets": { "qids": ["0", "1"] },
  "steps": [
    { "type": "OneQubitCheck", "mode": "scheduled" },
    { "type": "FilterByStatus" },
    { "type": "CustomOneQubit", "step_name": "coherence", "tasks": ["CheckT1", "CheckT2Echo"] }
  ],
  "default_run_parameters": { "shots": 1024 }
}
```

The spec cannot reference code. Each `type` maps to one Step class, task names must be enabled for the backend and match the step's task type, and anything else is rejected before dispatch.

## Endpoints

| Endpoint | Permission | Purpose |
| --- | --- | --- |
| `GET /calibration-pipelines/catalog` | viewer | Step types with their dependencies and default tasks, the backend's tasks by type, and the JSON schema of the spec |
| `POST /calibration-pipelines/validate` | viewer | Dry run: every problem with a path into the spec, plus the resolved steps and tasks when it would run |
| `POST /calibration-pipelines/execute` | editor | Validate, then run the spec as one execution through the worker's `system-calibration-pipeline` deployment |

`validate` never fails with a 422 for a bad spec. It returns `valid: false` and a `problems` list such as `targets.qids[1]: qubit '99' is not on chip 64Qv3`, so a caller can correct the spec. `execute` returns the same list in the 422 detail when the spec is not valid, and 503 when the worker has not registered the deployment yet.

## Steps

| Type | Kind | Runs | Needs before it |
| --- | --- | --- | --- |
| `ConfigureAll` | calibration | ConfigureAll for the targets' MUXes | nothing |
| `BringUp` | calibration | `BRINGUP_TASKS` or `tasks` | nothing |
| `OneQubitCheck` | calibration | `CHECK_1Q_TASKS` or `tasks` | nothing |
| `OneQubitFineTune` | calibration | `FULL_1Q_TASKS_AFTER_CHECK` or `tasks` | nothing |
| `CustomOneQubit` | calibration | `tasks` (qubit tasks) | nothing |
| `FilterByStatus` | transform | keeps qubits whose latest one-qubit step succeeded | `OneQubitCheck` or `OneQubitFineTune` |
| `FilterByMetric` | transform | keeps qubits with `metric >= threshold` | `OneQubitCheck` or `OneQubitFineTune` |
| `GenerateCRSchedule` | transform | plans parallel CR groups | candidate qubits |
| `TwoQubitCalibration` | calibration | `FULL_2Q_TASKS` or `tasks` | candidate qubits |
| `CustomTwoQubit` | calibration | `tasks` (coupling tasks) | candidate qubits |

One-qubit steps take `mode` (`synchronized`, `scheduled`, `simultaneous_spectroscopy`, `serial`). Custom steps take a `step_name` that must be unique within the pipeline; it is the step's name in execution history. Targets are either `qids` or `mux_ids` with optional `exclude_qids`.

The step order is checked the same way `Pipeline._validate` checks it in the worker: a step that lists several requirements needs at least one of them.

## Following a run

`CalibService.run` gives every calibration step its own execution; transform steps create none. The executions of one run share `note.flow_run_id`, carry `note.step_index`, and, for a spec run, `note.pipeline` with the planned steps. `GET /executions/{id}` on any of them returns a `pipeline` field that covers the whole run: the plan with each step's execution id, status (`pending`, `skipped` for transforms, or the execution's own), task counts, and the figures of its finished tasks. `pipeline.status` is `running` while any step runs or the run still holds the project lock between steps, and otherwise the outcome of the last step.

Readers that want the whole run use that field rather than the first execution's status, which completes when step 1 does. `QDashClient.waitForExecution` does so by default (`wholePipeline: false` waits for the single execution), so pi-qdash's `qdash_wait_execution` returns when the run ends, and the chat's execution card shows every step and figure as the run advances.

## Where the pieces live

| File | Role |
| --- | --- |
| `src/qdash/datamodel/calibration_pipeline.py` | The spec models, the step catalog (`STEP_CATALOG`), the default task lists, and the step-order check. Free of workflow imports so the API can validate without a Prefect runtime |
| `src/qdash/workflow/service/pipeline_flow.py` | The `calibration-pipeline` system flow: builds Step and Target objects from a spec and calls `CalibService.run` |
| `src/qdash/workflow/register_system_flows.py` | Registers `system-calibration-pipeline` on worker startup |
| `src/qdash/api/services/calibration_pipeline_service.py` | Chip, backend, task-type, and run-parameter checks; the catalog |
| `src/qdash/api/services/flow_service.py` | `execute_calibration_pipeline`: lock claim, Prefect run, execution row |
| `src/qdash/api/routers/calibration_pipeline.py` | The three endpoints |

`STEP_CATALOG` restates each Step class's `requires` and `provides`; `tests/qdash/workflow/service/test_pipeline_flow.py` asserts the two agree, so adding a Step means adding a spec model, a catalog entry, a `build_step` branch, and an entry in that test's `EVERY_STEP` list. The default task lists moved to the datamodel module for the same reason; `qdash.workflow.service.tasks` re-exports them.

## Agent use

The Copilot agent composes a spec from the catalog and the flow templates, validates it, and shows the resolved steps in an approval card before `execute` runs. The spec is the only thing the agent writes; the procedure it encodes still comes from the templates and Step classes, and the deterministic gates in the engine judge every task result as they do for a saved flow.
