# Task Calls

A task call is one planned invocation of a calibration task inside a step. Every step lists its
work as `TaskCall` entries, so one step can run the same task more than once with different
settings, and every result can be traced back to the call that produced it. The model is
`qdash.datamodel.task_call.TaskCall`, exported as `from qdash.workflow import TaskCall`; Python
flows and [pipeline specs](./calibration-pipeline.md) use the same class.

```python
from qdash.workflow import TaskCall, sweep
from qdash.workflow.service.steps import CustomOneQubit

CustomOneQubit(
    step_name="ramsey",
    tasks=[
        TaskCall(name="Configure", on_failure="stop"),
        TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run={"detuning": 0.001}),
        TaskCall(
            name="CheckRamsey",
            call_id="ramsey_fine",
            run={"detuning": 0.0002, "time_range": sweep.arange(0, 50_001, 500)},
        ),
    ],
    continue_on_failure=True,
)
```

A step rejects a plain task name such as `tasks=["CheckT1"]` when it is constructed, with a
pointer to the [migration](#migrate-saved-flows). Built-in steps (`OneQubitCheck`,
`OneQubitFineTune`, `BringUp`, `TwoQubitCalibration`) default to the call lists in
`qdash.workflow.service.tasks`.

A flow parameter annotated `list[TaskCall] | None`, as in the Simple Calibration, Fake Backend
Calibration, 2Q Calibration, and 2Q Scheduled Calibration templates, takes calls as JSON objects
in the `parameters` of `POST /flows/{name}/execute` (the pi `qdash_execute_flow` tool sends the
same body; the workflow editor's run dialog sends no `tasks`, so the source default applies), for
example:

```json
{
  "parameters": {
    "tasks": [
      {"name": "CheckRamsey", "call_id": "ramsey_coarse", "run": {"detuning": 0.001}},
      {"name": "CheckRamsey", "call_id": "ramsey_fine", "run": {"detuning": 0.0002}}
    ]
  }
}
```

Prefect validates the parameters against the flow signature on the worker, so each object
becomes a `TaskCall` before the flow body runs; a plain task name or an unknown field fails the
run before any task starts.

## Identity

Three identifiers describe a result, and none of them is a list position:

| Identifier | Scope | Set by |
| --- | --- | --- |
| `step_id` | One step in the plan | `step_id=` on a built-in step, `step_name` on a custom step, else the step's name |
| `call_id` | One call in its step | The author; defaults to the task name |
| `task_id` | One execution of a call on one target | The engine, as for every task result |

A task that appears once in a step may omit `call_id`. Every occurrence of a task that appears
more than once must carry its own `call_id`; `normalize_calls` raises otherwise, and also
when two calls share an id or a default id collides with an explicit one. Call ids match
`^[A-Za-z][A-Za-z0-9_.-]{0,63}$`, so task names are valid ids. Step ids match
`^[a-z][a-z0-9_]{0,63}$` and must be unique among the calibration steps of a pipeline:
`Pipeline` rejects two `OneQubitCheck` steps until one of them sets `step_id`.

The engine records the identity on each task result as `invocation`
(`qdash.datamodel.task_invocation.TaskInvocation`): `step_id`, `call_id`, `plan_digest`, and the
call's effective `settings`. `CalibService.run` stores the plan itself (`calibration_plan`:
steps, resolved calls, per-task defaults, shared run defaults, and the digest) in the note of
every step Execution. The task result's own run and input parameter snapshots remain the record
of what ran; the plan does not recreate hardware or calibration state. Results written before
task calls existed have no `invocation`.

## Settings

For one call, run and input values resolve from highest to lowest precedence:

1. The call's `run` and `input`
2. `CalibService(task_parameters=...)[task_name]`, the common per-task defaults
3. `default_run_parameters`, the shared run defaults
4. The task's `run_spec` and input resolution

`run` takes plain values, `{"value": ..., "value_type": ...}`, or the `sweep` helpers; `input`
takes plain values. Normalization is `qdash.datamodel.task_settings`, the same code
`task_parameters` uses. A field that is absent or `None` inherits from the next layer, so
`update_calibration_parameters=None` keeps the per-task or workflow policy instead of resetting
it. Engine and session constraints still apply to every layer; for example a call cannot set a
`readout_duration` that differs from the Qubex session. See
[Parameter Resolution](./parameter-resolution.md) for how each layer reaches the task.

## Failure Policy

`continue_on_failure` on a step sets the default for its calls; `on_failure` on a call
overrides it. `"stop"` skips the same target's remaining calls in the step after this call
fails, and `"continue"` runs them. The scope is one target: qubit 0 failing a call never stops
qubit 1. Skipped calls stay in the result with `reason` `stopped_after_failure`.

A call that fails or fails its quality check writes nothing to the calibration database, so the
next call resolves its inputs from the last accepted value. A successful call that updates
calibration parameters is visible to the next call on the same target through the normal
database resolution; in the example, `ramsey_fine` reads the qubit frequency that `ramsey_coarse`
accepted.

## Scheduling

Calls do not change how a step schedules its targets:

| Path | Unit of work | Synchronization |
| --- | --- | --- |
| `serial`, `scheduled`, `synchronized`, two-qubit groups | One target runs every call in order (`run_target_calls`) | Targets do not wait for each other between calls |
| `simultaneous_spectroscopy` | One call runs once over a batch of qubits (`run_batch_calls`) | Each call is a barrier for its batch |
| Step boundary | The pipeline finishes the step's Execution | All targets |

MUX tasks run only on the MUX representative; the other qubits record the call as skipped with
`reason` `not_mux_representative`. The batch path rejects calibration input overrides and tasks
without `batch_run` in `OneQubitStageRunner.preflight_batch` before the first batch measures; the
pipeline API reports the input case at validation time.

## Results

Each target's step result keeps every call in order. `QubitCalibData.calls` and
`CouplingCalibData.calls` return `TaskCallResult` entries with `call_id`, `name`, `status`,
`task_id`, `output`, and `error`; `call(call_id)` reads one call and `latest_call(name)` the last
call of a task. A target's status is `failed` when any of its calls failed. The same entries
are recorded in the Execution's stage results, and `StepContext.get_step_result(step_id)` returns
any earlier step's result.

Built-in steps derive their metrics, such as `x90_fidelity`, from the last call of each task. A
failed last call yields no metric; an earlier call of the same task never stands in for it.

`FilterByStatus` and `FilterByMetric` read:

- with `step` and `call_id`, that call: the qubit passes only when the call succeeded and, for a
  metric, its output parameter meets the threshold;
- with `step` only, that step's status or step-level metrics; custom steps have no step-level
  metrics, so a metric filter on one needs `call_id`;
- with neither, the latest `OneQubitFineTune` or `OneQubitCheck` result, as before task calls.

The filter decides from completion and acceptance in this run, not from the latest value in the
calibration database. For one call's stored results, query
`GET /task-results?execution_id=...&step_id=...&call_id=...`.

## Re-execution

Single-task re-execution restores the exact `task_id`, as before. Execution re-execution
(`source_execution_id`) matches each new call to the source result with the same task, qid,
`step_id`, and `call_id`, so the coarse and fine `CheckRamsey` each restore their own settings.
A source result from before task calls is used when it is the only one for its task and qid;
several such results raise `SnapshotAmbiguityError` instead of picking one. Re-execution does not
retry or resume a run and makes no claim that repeating a hardware call is idempotent.

## Migrate Saved Flows

`python -m qdash.common.migration.task_calls` inventories saved flows (the user flows directory
by default, or the paths given) and reports each place that still uses task names. It parses the
source with `ast` and never imports or runs a flow.

```bash
python -m qdash.common.migration.task_calls                       # report only
python -m qdash.common.migration.task_calls --write-to /tmp/converted user_flows/alice
```

With `--write-to` it writes converted copies to that directory and leaves the originals unchanged.
It converts a literal task-name list passed to a step into `TaskCall` entries, and so does it for
a variable assigned such a list once and used only as `tasks=` arguments; a name repeated in one
list gets `call_id` values `<Task>`, `<Task>_2`, and so on, which you should rename to describe
each call. It turns `stop_on_failure_tasks` on the same step into `on_failure="stop"`. Names
resolve with Python's scoping rules, so a function-local variable that shadows a module-level
list is judged by its own assignment.

It reports, without changing, every `tasks=` value it cannot prove holds `TaskCall` entries: a
list built at run time, a variable that is not assigned in the file, reassigned, appended to with
something other than a `TaskCall`, or imported from a module outside `qdash`, and a flow parameter
annotated `list[str]` or not annotated at all. It also reports a task-name list that is used
outside `tasks=` or shared by steps with different `stop_on_failure_tasks`, step-level
`task_parameters`, and the deprecated `CalibService(task_run_parameters=...)`. The exit status is
0 when nothing needs attention, 1 when a file needs conversion or manual changes, and 2 when a
file cannot be read.

## Testing

`tests/qdash/workflow/test_task_call_pipeline_e2e.py` runs a step with two `CheckRamsey` calls on
the fake backend and checks task ids, upstream links, per-call settings, accepted-write
propagation, the call filter, and re-execution. `tests/qdash/workflow/service/test_task_call_propagation.py`
covers each scheduling path, and `tests/qdash/common/test_task_call_migration.py` the migration.
`tests/qdash/workflow/test_task_call_plan_digest_e2e.py` runs an API-validated spec through
`calibration_pipeline` with isolated worker sessions and checks that every step execution stores
the API's `plan_digest` as `note.pipeline.spec_digest` and every task result carries
`note.calibration_plan.digest`. `tests/qdash/workflow/test_task_call_flow_parameters.py` runs
`task_call_flow_contract.py` with real Prefect in a separate interpreter, because the suite stubs
`prefect`, and checks that each template turns JSON calls into `TaskCall` entries.

## Implementation Files

- `src/qdash/datamodel/task_call.py`: `TaskCall`, `TaskSettings`, `StepCalls`, `normalize_calls`
- `src/qdash/datamodel/task_invocation.py`: `TaskInvocation`
- `src/qdash/datamodel/task_settings.py`: settings normalization shared with `task_parameters`
- `src/qdash/workflow/service/_internal/call_runner.py`: per-target and batch call execution
- `src/qdash/workflow/service/steps/filters.py`: step and call references
- `src/qdash/workflow/engine/task/snapshot_loader.py`: call-aware snapshot lookup
- `src/qdash/common/migration/task_calls.py`: saved-flow migration
