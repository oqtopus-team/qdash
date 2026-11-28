# Task Calls

A `TaskCall` gives one task occurrence its own settings, identity, and results.
Python flows and [pipeline specs](./calibration-pipeline.md) use the same model.

```python
from qdash.calibration import CustomOneQubit, TaskCall

CustomOneQubit(
    step_name="ramsey",
    tasks=[
        TaskCall(name="Configure", on_failure="stop"),
        TaskCall(name="CheckRamsey", call_id="coarse", run={"detuning": 0.001}),
        TaskCall(name="CheckRamsey", call_id="fine", run={"detuning": 0.0002}),
    ],
)
```

## Identity

| ID | Scope |
| --- | --- |
| `step_id` | Unique calibration step in a pipeline; custom steps use `step_name` |
| `call_id` | Unique call in that step; defaults to the task name |
| `task_id` | Engine-assigned result for one call on one target |

Every occurrence of a repeated task needs an explicit call ID. Call IDs match
`^[A-Za-z][A-Za-z0-9_.-]{0,63}$`; step IDs match `^[a-z][a-z0-9_]{0,63}$`.
Results record `invocation` with the step, call, settings, and plan digest. Each execution stores
the plan; recorded input and run snapshots remain the evidence of what actually ran.

## Settings

Set `run` for experiment settings, `input` for allowed calibration overrides, and
`update_calibration_parameters=False` for measurement-only output. Absent or `None` fields
inherit. Calls override per-task defaults, shared run defaults, and task defaults in that order.
Use plain input values and plain or `sweep` run values. Session constraints still apply; see
[Parameter Resolution](./parameter-resolution.md).

## Failure Policy

`on_failure="stop"` skips that target's remaining calls; `"continue"` runs them. An unset value
inherits the step's `continue_on_failure`. One target's failure does not stop another target.
Failed outputs do not replace accepted calibration values.

## Scheduling

Ordinary targets run their complete call list independently. Round and step boundaries wait for
all their targets. `simultaneous_spectroscopy` instead runs each call over a batch and rejects
input overrides or tasks without batch support before measuring. MUX tasks run only on their
representative qubit; other members record a skipped call.

## Results

Use `data.calls`, `data.call(call_id)`, or `data.latest_call(name)`. Any failed call makes its
target's step status failed. Built-in metrics use the last call of a task, never an earlier
successful call in place of a failed last call.

Filters with `step` and `call_id` read that exact call; with only `step`, they read step status
or metrics. Custom-step metric filters need a call ID. Without `step`, filters read the latest
`OneQubitFineTune` or `OneQubitCheck`. Filters use this run's results, not current database values.
Stored results can be queried by `execution_id`, `step_id`, and `call_id`.

## Re-execution

Snapshot lookup matches task, target, step, and call. Legacy results without invocation metadata
are usable only when unambiguous; otherwise lookup fails. Re-execution is not an idempotent retry.

## Migrate Saved Flows

Back up saved flow sources before editing. QDash does not rewrite them automatically.

1. Replace task-name strings with `TaskCall(name=...)`; annotate task-list parameters as
   `list[TaskCall] | None`.
2. Give repeated calls and steps distinct IDs.
3. Replace `stop_on_failure_tasks` with `on_failure="stop"` on those calls.
4. Move per-occurrence settings onto calls.
5. Replace raw task-name result lookup with the call accessors above.
6. Give filters explicit step/call references when they must select a particular result.

Test on the Fake backend and inspect call IDs and effective settings before hardware use.
Older results remain readable without `invocation`.

## Migrate per-task defaults

`CalibService` rejects `task_parameters` and `task_run_parameters`. Merge each task's old settings
into every call of that task, preserving values already set on the call, including explicit
`True` and `False`. Apply old `task_run_parameters` first, then `task_parameters`.
Keep call IDs, order, and failure policies unchanged.

Shared run values can remain in `default_run_parameters`. A standalone step takes its own call,
for example `ConfigureAll(call=TaskCall(name="ConfigureAll", run={"configuration_mode": "ge-ef-cr"}))`.
Its target-derived MUX IDs still override the call's `run.mux_ids`. Compare effective settings
before and after migration. Pipeline specs still accept deprecated per-task defaults with a warning.

## Migrate session write-back

`CalibService(persist_output_parameters=...)` is removed. Set
`update_calibration_parameters=False` on **every** call that must remain measurement-only;
unset calls write back by default. A custom step passes the setting in each
`session.execute_task(..., parameters={"update_calibration_parameters": False})` call.
See [output persistence](./parameter-resolution.md#output-persistence) for single-task APIs.

## Testing

Run `task test-workflow`. Propagation tests are in
`tests/qdash/workflow/service/test_task_call_propagation.py`; flow-parameter tests are in
`tests/qdash/workflow/test_task_call_flow_parameters.py`.

## Implementation Files

- `src/qdash/datamodel/task_call.py`: identity and normalization
- `src/qdash/datamodel/task_settings.py`: settings
- `src/qdash/workflow/service/_internal/call_runner.py`: execution
- `src/qdash/workflow/service/steps/filters.py`: result selection
- `src/qdash/workflow/engine/task/snapshot_loader.py`: snapshot matching
