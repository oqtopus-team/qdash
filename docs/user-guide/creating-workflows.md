# Creating Workflows

Create a workflow from a template to save and repeat a calibration procedure. You need project
edit permission; use the Fake backend to learn without hardware.

## Start from a Template

1. Open **Workflow → New Flow**.
2. Choose **TEMPLATE** before editing; changing it replaces the editor contents.
3. Enter a unique **Flow Name** using letters, digits, and underscores.
4. Check **Chip ID** and **Entrypoint Function** against the flow function in the source.
5. Edit the source, then select **Save Flow**.

**Save Flow** creates a new workflow; it does not replace an existing name. To change an existing
flow, open it and select **Edit**, then **Save**.

## Name the Calibration Group

Templates declare the name shown for a new calibration group:

```python
@calibration_flow(session_name="Coherence check")
```

Change the quoted string to describe the work. Use a non-empty string literal of at most
500 characters after trimming whitespace; saving rejects expressions and invalid names so
manual and scheduled launches use the same name. Omit `session_name` or use `None` for the
default name. This name is separate from **Flow Name** and the Python function
name. Launching into an existing CalibrationSession preserves that group's name.

The template creates `CalibrationSession.from_context(context)` and calls `session.run()`.
Several calls inside the same workflow run stay in the same group and recorded run. Existing
saved flows using `CalibService` still work; follow the
[migration steps](../developer-guide/workflow/quickstart.md#preserve-terminal-handling) when editing them.

## Choose the Targets

A MUX is a group of qubits sharing multiplexed readout. Use `mux_ids` for whole MUXes, `exclude_qids` to omit qubits, or `qids` for individual qubits.
Standard templates give MUX targets priority. The **Execute** dialog can override supported
targets for one run; schedules use the saved defaults.

In **Simple Calibration**, add a default before the target-construction block when needed:

```python
if mux_ids is None and qids is None:
    mux_ids = [0]
```

Replace `0` with the intended MUX, or assign `qids = ["0", "1"]` instead.

## Run Box Setup Before Spectroscopy

On QuEL-1 or QuEL-3, select **Box Setup** to run **CorrectCaptureDelay** once per selected MUX.
Supply `mux_ids` in the source or **Execute**, then inspect the result before spectroscopy.

## Choose Tasks and Execution Order

Tasks run in list order. Find names in **Tasks**. In **Simple Calibration**, edit the list after
`else` in the `CustomOneQubit` step's `tasks=` argument:

```python
CustomOneQubit(
    step_name="simple_tasks",
    tasks=tasks if tasks is not None else [
        TaskCall(name="CheckRabi"),
        TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32}),
        TaskCall(name="CheckHPIPulse"),
    ],
    execution_mode=execution_mode,
),
```

Keep the template's `TaskCall` import and the conditional so run-time task selections still work.

Keep configuration and measurement tasks in the required order. Give repeated occurrences
unique `call_id` values, such as `ramsey_coarse` and `ramsey_fine`.

### Choose an Execution Mode

| `execution_mode` | Behavior |
| --- | --- |
| `parallel_by_mux` | MUXes run independently; qubits within each MUX run in order |
| `parallel_by_round` | One qubit per MUX per round; wait for the round to finish |
| `sequential` | One qubit at a time |
| `manual` | Run the [rounds you specify](./manual-execution-rounds.md) |
| `simultaneous_spectroscopy` | Experimental batch measurement for supported tasks |

Each qubit runs its own task list; parallel modes do not synchronize pulses. Templates such as
**Simple Calibration** default to `parallel_by_mux`; directly constructed one-qubit steps default
to `parallel_by_round`. Set the mode explicitly when order matters.

Use `sequential` until the deployment has verified its parallel hardware capability, especially
with `<box ID>:<port>` wiring. See [parallel-execution checks](./setup/qubex-backend.md#check-parallel-execution-on-quel-3).
**Execution help** in the editor explains the modes without running anything.

## Schedule Two-Qubit Calibration

Choose the template for your targets:

| Template | Targets |
| --- | --- |
| **2Q Calibration from Qubits** | Connected `qids`; QDash chooses directed pairs |
| **2Q Automatic Pairs** | Explicit `coupling_pairs`; QDash groups them |
| **2Q Manual Rounds** | [Exact pairs and rounds](./manual-execution-rounds.md#write-two-qubit-rounds) |

Automatic groups avoid modeled hardware conflicts and run in order. Each pair runs its task
list independently within a group. `max_parallel_ops` defaults to 10 in these automatic templates;
use 1 for one pair at a time. It limits group size, not hardware capability. `inverse` reverses
the selected direction in **2Q Calibration from Qubits**.

Filter one-qubit results before generating a CR schedule. A later step reuses an existing
schedule, so set its cap on `GenerateCRSchedule`. The removed `SetCRSchedule` must be replaced
by manual rounds or `CouplingTargets` with automatic grouping.

## Set Parameters for One Task

Put experiment settings in `run`, calibration overrides in `input`, and output-saving policy
on each call:

```python
from qdash.calibration import TaskCall, sweep

TaskCall(
    name="CheckRamsey",
    run={"shots": 1024, "time_range": sweep.arange(0, 10_000, 100)},
    input={"control_frequency": 7.012},
    update_calibration_parameters=False,
)
```

This example keeps outputs in history without making them current values. Use `default_run_parameters`
on `session.run()` for run settings shared by every task. The removed `CalibService` arguments `task_parameters`
and `task_run_parameters` must move into individual calls. See [Task Calls](../developer-guide/workflow/task-calls.md).

## Use Earlier Calibration Results in Later Steps

Accepted outputs become inputs for later tasks, including across steps. History-only outputs do
not replace current values; explicit input overrides take priority. Check effective inputs on
**Execution**.

## Update a Flow Saved Before Task Calls

Replace task-name strings with `TaskCall(name="...")`, give repeats unique `call_id` values,
and replace `stop_on_failure_tasks` with `on_failure="stop"` on those calls. See
[Task Calls](../developer-guide/workflow/task-calls.md) for result lookups and per-call settings.

## Update a Flow That Uses the Former Mode Names

Rename `mode` to `execution_mode`, `serial` to `sequential`, `scheduled` to `parallel_by_mux`,
and `synchronized` to `parallel_by_round`. The former names fail validation.

## Save and Test the Workflow

Save, select **Execute**, and inspect **Execution preview**. Test on a small target before
adding a schedule or expanding it. A workflow reserves the whole chip until its steps finish.

## Inspect Step Results

Each step reached by a run appears in **Execution**, including filters and schedule generation.
For those steps, **Step outcome** shows the selected targets, exclusion reasons or scheduled
groups. They have no measurement tasks or figures. Pipeline progress marks unreached steps as
**Not reached**, and transforms from older runs as **Not recorded**; old missing results are
not reconstructed.

## Organize Your Workflows

Use **Explorer** to move workflows into folders within their creator's space, or set a path
such as `daily/t1` in **Folder**. Moving changes the listing, not the source, schedules, or history.
