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

A flow has an entrypoint, targets, ordered steps, and `CalibrationSession.run(targets, steps)`.
Keep `username`, `chip_id`, `flow_name`, and `project_id` in the signature so QDash can inject
execution context. Build the context and session explicitly:

```python
from qdash.calibration import CustomOneQubit, QubitTargets, TaskCall
from qdash.workflow import CalibrationSession, calibration_flow, resolve_calib_context


@calibration_flow(session_name="Coherence check")
def coherence(username: str, chip_id: str, qids: list[str],
              flow_name: str | None = None, project_id: str | None = None):
    context = resolve_calib_context(username, chip_id, project_id=project_id)
    session = CalibrationSession.from_context(context)
    return session.run(
        targets=QubitTargets(qids),
        steps=[CustomOneQubit(
            step_name="coherence",
            tasks=[TaskCall(name="Configure"), TaskCall(name="CheckT1")],
        )],
        name=flow_name,
    )
```

This server-side example needs the workflow dependencies, configured database/backend, an existing
user/chip/project, and CheckT1's required calibration. For a script connecting over HTTP, use the
[Python SDK](../../reference/clients/python.md#run-a-calibration); both use `qdash.calibration`
targets, steps, and task calls.

`session_name` is a string literal naming the automatic group created for a launch. A launch
into an existing CalibrationSession keeps its name. Calls inside one flow run share that
launch's recorded run and session; they do not start nested remote runs. Each `run()` waits
for its own steps and returns `CalibrationResult`; step exceptions propagate to Prefect.

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

Shared definitions derive from `qdash.calibration.ExecutionStep`. Constructing one performs no
I/O. Every step the run reaches creates an Execution: calibration steps record measurements;
transform steps record filtering or scheduling outcomes without connecting hardware or publishing
calibration data. `StepSequence` validates dependencies before running.
Runtime custom steps implement `execute(session, targets, ctx)` and use `self.step_calls(session)`;
that `session` is the internal runtime, not the public CalibrationSession. Custom steps remain
worker-only and need their own source-preview support.
Keep task lists visible in templates. Repeated tasks need distinct call IDs; repeated steps need
distinct step IDs. See [Task Calls](./task-calls.md).

## State Between Steps

`StepContext` carries candidates, schedules, and typed results between steps. Accepted calibration
values persist in MongoDB and are resolved by later task preprocessing. Measurement-only outputs
do not replace them. Each reached step opens a new execution; parallel measurement workers borrow its
settings and reservation rather than sharing Python objects.

See [Parameter Resolution](./parameter-resolution.md) and
[Calibration Data Lifecycle](./calibration-data-lifecycle.md).

## Set Task Parameters

Set `run`, `input`, and `update_calibration_parameters` on each `TaskCall`. Pass
`default_run_parameters` to `session.run()` for shared run defaults. Sweeps use `sweep.linspace`,
`sweep.logspace`, `sweep.arange`, `sweep.range`, or `sweep.values`.
Removed service arguments must follow the [migration guide](./task-calls.md#migrate-per-task-defaults).

## Preserve Terminal Handling

`@calibration_flow` registers cancellation, failure, and crash hooks to finalize interrupted
records and release owned reservations. Explicit hook options replace those defaults. Nested
flows borrowing another run's reservation must use the `*_keep_lock` hooks from
`qdash.workflow.service.calib_service`.

Existing `@flow` and `CalibService` sources remain supported. To migrate, back up the source,
use shared definitions from `qdash.calibration`, construct `CalibrationSession.from_context`,
and move defaults and tags to `session.run()`. Pass `name=flow_name` there. Replace the top-level
hook block with `@calibration_flow(session_name="...")`; preserve custom or borrowing hooks.
Test the edited source on Fake and inspect **Execution preview** before using hardware.

## Test the Template

Use a recording service to check target precedence, missing targets, step order, and call settings.
Run the matching template test, then `task test-workflow`; see [Workflow Testing](./testing.md).
