# Workflow Authoring Quickstart

Start with a flow template and change its targets, steps, and task calls.
For the editor procedure, see [Creating Workflows](../../user-guide/creating-workflows.md).

## Start from an Existing Template

Copy the closest file in `src/qdash/workflow/templates/`. Keep its context parameters, target
validation, and terminal hooks. Register new editor templates in `templates/templates.json`
with the backend they support. For a hardware-free first change, start with `fake_backend.py`
and `tests/qdash/workflow/test_fake_backend_template.py`. Change its task list or targets, then run:

```bash
uv run pytest tests/qdash/workflow/test_fake_backend_template.py -v
```

The test checks the declared plan without measuring. To try the flow in the application, use
[Creating Workflows](../../user-guide/creating-workflows.md) on a Fake deployment, save your edited
source as a new flow, and inspect its run in **Execution**.

## Define a Flow

A flow has four parts: a Prefect entrypoint, targets, ordered steps, and
`CalibService.run(targets, steps)`. Keep `username`, `chip_id`, `flow_name`, and `project_id`
in the signature so QDash can inject the execution context. The service checks project write
permission and closes its executions; no finish call is needed.

Outside Prefect, use a checked context:

```python
from qdash.workflow import CalibService, TaskCall, resolve_calib_context
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import QubitTargets

context = resolve_calib_context("alice", "64Qv3", project_id="my-project")
steps = [CustomOneQubit(
    step_name="coherence",
    tasks=[TaskCall(name="Configure"), TaskCall(name="CheckT1")],
)]
CalibService.from_context(context).run(QubitTargets(["0"]), steps)
```

This is a server-side example: it needs the workflow dependencies, configured database/backend,
an existing user/chip/project, and CheckT1's required calibration. It starts measurements and
publishes accepted outputs. For a script connecting to a running deployment over HTTP, use the
[Python SDK](../../reference/clients/python.md#run-a-calibration) instead.

## Choose Targets

| Target | Selection |
| --- | --- |
| `MuxTargets` | Topology members of selected MUXes, minus exclusions |
| `QubitTargets` | Explicit qubits |
| `CouplingTargets` | Directed pairs and their endpoint qubits |
| `AllMuxTargets` | Every MUX |
| `AllQubitTargets` | Every qubit, including standalone qubits |

Standard templates prefer `mux_ids` over `qids` and reject a missing selection.
A targeted MUX needs wiring; `AllMuxTargets` rejects topologies with no MUXes.

## Compose Steps

A `CalibrationStep` performs hardware work and creates an execution. A `TransformStep` filters
or schedules candidates without creating one. `Pipeline` validates dependencies before running.
Custom steps implement `execute(session, targets, ctx)` and use `self.step_calls(session)`.
Keep task lists visible in templates. Repeated tasks need distinct call IDs; repeated steps need
distinct step IDs. See [Task Calls](./task-calls.md).

## State Between Steps

`StepContext` carries candidates, schedules, and typed results between steps. Accepted calibration
values persist in MongoDB and are resolved by later task preprocessing. Measurement-only outputs
do not replace them. Each hardware step opens a new execution; parallel workers borrow its
settings and reservation rather than sharing Python objects.

See [Parameter Resolution](./parameter-resolution.md) and
[Calibration Data Lifecycle](./calibration-data-lifecycle.md).

## Set Task Parameters

Set `run`, `input`, and `update_calibration_parameters` on each `TaskCall`. Use
`default_run_parameters` only for shared run defaults. Sweeps use `sweep.linspace`,
`sweep.logspace`, `sweep.arange`, `sweep.range`, or `sweep.values`.
Removed service arguments must follow the [migration guide](./task-calls.md#migrate-per-task-defaults).

## Preserve Terminal Handling

Top-level flows register `on_flow_cancellation`, `on_flow_failure`, and `on_flow_crashed` from
`qdash.workflow.service.calib_service`. They finalize interrupted records and release owned
reservations. Use `*_keep_lock` hooks only for nested flows borrowing another run's reservation.

## Test the Template

Use a recording service to check target precedence, missing targets, step order, and call settings.
Run the matching template test, then `task test-workflow`; see [Workflow Testing](./testing.md).
