# Creating Workflows

Create a workflow from a built-in template when the same ordered calibration procedure must be
saved, shared, run, or scheduled for a project.

Creating and changing workflows requires project edit permission. Start with the Fake backend
when you are learning the editor or checking a new task sequence without laboratory hardware.

## Start from a Template

1. Confirm the active project, then open **Workflow**. Saved workflows are listed in one folder
   per creator, with the subfolders set by each workflow's **Folder** property inside. Your own
   folder comes first and starts open; select another creator's folder header to open it.
2. Select **New Flow**.
3. Under **TEMPLATE**, confirm the backend; the configured default backend is preselected, and
   the list holds only the templates written for it, so a Fake backend never offers hardware
   templates. Then select the workflow closest to the procedure you need. **Simple Calibration**
   is the smallest general-purpose starting point on the qubex backend.
4. Under **PROPERTIES**, enter a unique **Flow Name** using letters, numbers, and underscores.
5. Confirm **Entrypoint Function**, **Username**, and **Chip ID**. The entrypoint must match the
   function marked as the flow in the source.
6. Edit the source, then select **Save Flow**.

**Save Flow** only creates a workflow. When the project already has a workflow with that name,
including one created while you were editing, nothing is saved: the page keeps your source and
properties and asks for another **Flow Name**. To change an existing workflow, open it and
select **Save**, which replaces it.

Selecting another template replaces the current editor contents. Choose the template before
making source changes.

| Property | Meaning |
| --- | --- |
| **Flow Name** | Project-unique name of the saved workflow; it cannot be renamed later |
| **Description** | Purpose and expected use of the workflow |
| **Entrypoint Function** | Function QDash starts when the workflow runs |
| **Username** | Required default shown in the editor; the signed-in user owns each execution |
| **Chip ID** | Chip reserved while the workflow runs |
| **Tags** | Comma-separated labels added to execution history |
| **Folder** | Optional `a/b` path that files the workflow under subfolders in your space on the **Workflow** page; see [Organize your workflows](#organize-your-workflows) |

Saving checks the Python syntax and entrypoint, then registers the workflow for execution. Correct
any reported source, entrypoint, or registration error and save again.

## Choose the Targets

Set either MUX targets or individual qubit targets in the template. Standard templates give MUX
targets priority when both are present.

| Source value | Use it for |
| --- | --- |
| `mux_ids` | All qubits belonging to one or more MUXes |
| `exclude_qids` | Qubits to remove from a MUX selection |
| `qids` | An explicit list of individual qubits |

For an immediate run, select targets in **Execute Flow** as described in
[Run a Workflow](./running-calibrations.md#run-a-workflow). Changes in that dialog apply only to
that run and do not change the saved source or schedules.

For scheduled runs, give the template a safe default target. In **Simple Calibration**, add this
fallback immediately before the block that creates the targets:

```python
if mux_ids is None and qids is None:
    mux_ids = [0]
```

Replace `0` with the MUX that the saved workflow should use. To target individual qubits instead,
set `qids = ["0", "1"]`. If every caller supplies targets through an API, leave the template's
missing-target check unchanged instead of adding a fallback.

## Run Box Setup Before Spectroscopy

Use **Box Setup** on QuEL-1 or QuEL-3 hardware to align each selected MUX's readout capture
before running resonator spectroscopy. The template requires `mux_ids` and runs
**CorrectCaptureDelay** once per MUX.

1. Select **Box Setup** under **TEMPLATE** and set a flow name.
2. For an immediate run, select **MUX IDs** in **Execute Flow**. For scheduled runs, set a
   default MUX target in the source by replacing the template's missing-target check with:

   ```python
   if mux_ids is None:
       mux_ids = [0]
   ```

   Replace `0` with the MUX you want to align.
3. Save the flow, then select **Execute**. Review the capture delay result before running a
   spectroscopy workflow.

## Choose Tasks and Execution Order

The task list runs from top to bottom. Open **Tasks** in another tab to find the task names enabled
for the active backend, then replace the default list in the template. In **Simple Calibration**,
edit the default list after `else` in the `tasks=` argument of `CustomOneQubit` in the flow
function. Keep the condition so tasks supplied at execution time still override the default:

```python
CustomOneQubit(
    step_name="simple_tasks",
    tasks=tasks
    if tasks is not None
    else [
        TaskCall(name="CheckRabi"),
        TaskCall(name="CreateHPIPulse", run={"hpi_duration": 32}),
        TaskCall(name="CheckHPIPulse"),
    ],
    mode=mode,
),
```

The `run={"hpi_duration": 32}` setting belongs to that `CreateHPIPulse` call only. A replacement
list runs each call with only the settings that call sets.

Keep configuration tasks and measurement tasks in their required order. A later task reads the
calibration state produced or applied by earlier tasks.

To run a task twice in the same step, for example a coarse and a fine Ramsey measurement, give
each occurrence its own `call_id` and its own settings:

```python
TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run={"detuning": 0.001}),
TaskCall(name="CheckRamsey", call_id="ramsey_fine", run={"detuning": 0.0002}),
```

Each call appears as its own task in the execution, labeled with its call ID. A list of plain task
names such as `"CheckT1"` stops the flow before it measures; see
[Update a flow saved before task calls](#update-a-flow-saved-before-task-calls).

The `execution_mode` value controls how the selected qubits wait for each other. In every mode
except `simultaneous_spectroscopy`, each qubit runs the step's whole task list before it counts as
finished; no mode runs one task across all qubits before the next task.

| Execution mode | Behavior |
| --- | --- |
| `parallel_by_mux` | MUXes run in parallel and the qubits of one MUX run one after another; each MUX moves on as soon as its current qubit finishes. The default for templates such as **Simple Calibration** |
| `parallel_by_round` | Qubits run in rounds of qubits from different MUXes; the next round starts after every qubit of the current round finishes |
| `sequential` | One MUX and one qubit at a time |
| `simultaneous_spectroscopy` | Experimental: each supported spectroscopy task measures a batch of qubits together |

For example, with qubits 0 and 1 on MUX 0 and qubits 4 and 5 on MUX 1, `parallel_by_mux` can
start qubit 1 when qubit 0 finishes while qubit 4 is still running. `parallel_by_round` finishes
both qubit 0 and qubit 4 before qubits 1 and 5 start. QDash chooses the actual grouping and order
from the chip wiring. `sequential`, `parallel_by_mux`, and `parallel_by_round` keep the same
hardware-sharing limits; changing between them changes only how qubits wait for each other.

Keep the template's execution mode unless the procedure requires a specific ordering. The
selected tasks must support the chosen mode and backend. Flows written before this setting was
renamed still run: the former `mode` parameter and the names `scheduled`, `synchronized`, and
`serial` are deprecated aliases of `execution_mode`, `parallel_by_mux`, `parallel_by_round`, and
`sequential`, and the run log shows a deprecation warning for them.

## Schedule Two-Qubit Calibration

Use **2Q Calibration** after the candidate qubits have the one-qubit calibration values
required by the selected tasks. CR (cross-resonance) scheduling chooses directed coupling pairs
and groups pairs that can run together without sharing qubits or conflicting hardware.

1. Open **New Flow** and choose **2Q Calibration** under **TEMPLATE**.
2. Set a default `qids` list in the source for runs started from the application, as described in
   [Choose the Targets](#choose-the-targets). Include at least two connected qubits.
3. Set the direction and parallelism defaults in the source using the settings below.
4. Keep the template's task list or select the coupling tasks required by your procedure.
5. Save and test the workflow on a small target before expanding it.

| Source setting | Meaning | Default |
| --- | --- | --- |
| `inverse` | Reverse the selected CR direction; check that your procedure supports this direction | `False` |
| `max_parallel_ops` | Maximum coupling pairs in one parallel group; hardware conflicts can reduce this number | `10` |

Groups run one after another. Within a group, coupling pairs can run in parallel, and each pair
runs its task list from top to bottom. A pair can advance to its next task while another pair is
still measuring. Pairs within one MUX are scheduled before pairs across MUXes. If no eligible pair
remains after direction and hardware checks, scheduling fails.

In a combined one-qubit and two-qubit workflow, filter the one-qubit results before generating
the CR schedule so the two-qubit work uses only the remaining candidates.

How this works: [CR Gate Scheduler](../developer-guide/architecture/cr-scheduler.md).

## Set Parameters for One Task

Set `run`, `input`, and `update_calibration_parameters` on a `TaskCall` when one call needs
different run settings, calibration inputs, or output-saving behavior. The settings apply to that
call only:

```python
from qdash.workflow import TaskCall, sweep

TaskCall(
    name="CheckRamsey",
    run={
        "shots": 1024,
        "time_range": sweep.arange(0, 10_000, 100),
    },
    input={"control_frequency": 7.012},
    update_calibration_parameters=False,
),
```

Values under `run` control the experiment. Use `sweep.linspace`, `sweep.logspace`,
`sweep.arange`, or `sweep.range` for generated ranges so their construction remains visible in the
workflow, or `sweep.values(0, 4, 16, 64)` for points you list yourself. A parameter that the task
defines as one kind of range accepts any of these forms. Other run parameters use plain values.
Values under `input` replace the current calibration input for every selected target in that call.
Set `update_calibration_parameters` to `False` for an exploratory measurement whose outputs must
remain in history without becoming the current calibration values.

When several calls need the same settings, keep them in a variable and reuse it in each
`TaskCall`:

```python
RAMSEY_RUN = {"shots": 1024}

TaskCall(name="CheckRamsey", call_id="ramsey_coarse", run={**RAMSEY_RUN, "detuning": 0.001}),
TaskCall(name="CheckRamsey", call_id="ramsey_fine", run={**RAMSEY_RUN, "detuning": 0.0002}),
```

Run settings that every task shares, such as `interval`, belong in the workflow's
`default_run_parameters`.

Older workflows may pass `task_parameters` or `task_run_parameters` to `CalibService` to give every
call of a task the same settings. QDash no longer accepts them, and such a workflow fails before
it measures, with an error that names the argument. To fix it, copy each task's settings into
every call of that task, keeping any value the call already sets, as
[Migrate per-task defaults](../developer-guide/workflow/task-calls.md#migrate-per-task-defaults)
shows.

QDash rejects a parameter placed in the wrong section, a parameter the task does not declare, or
an input the task does not allow users to override. See [Task Parameters](./task-parameters.md)
before overriding calibration inputs or allowing outputs to update shared state.

## Use Earlier Calibration Results in Later Steps

Later tasks use earlier outputs once those outputs pass validation and become current
calibration values. This also applies across workflow steps: finishing a step does not reset
the accepted values. Experiment settings such as shots and sweep ranges come from the workflow's
settings and task defaults, rather than from previous measurement outputs.

For example, if a frequency measurement changes the accepted frequency from 5.000 GHz to
5.010 GHz, a later task that uses that calibration value resolves 5.010 GHz. If the measurement
is configured to keep outputs only in history, the later task continues to use 5.000 GHz.
An explicit input override takes priority over either value.

Review the effective inputs in **Execution** to confirm what the later task actually used.
How this works: [State Between Steps](../developer-guide/workflow/quickstart.md#state-between-steps).

## Update a Flow Saved Before Task Calls

A flow saved before task calls lists tasks by name, such as `tasks=["Configure", "CheckT1"]`, and
stops before it measures. Edit the flow in **Workflow**:

1. Add `from qdash.workflow import TaskCall` to the imports.
2. Replace each task name with `TaskCall(name="...")`. Where the same task appears more than once
   in one list, add a `call_id` that describes each occurrence, for example
   `call_id="configure_readout"`.
3. Replace `stop_on_failure_tasks=("Configure",)` with `on_failure="stop"` on the listed calls.
4. Save the flow and run it on a small target.

Check the call IDs and settings of the run in **Execution** before running the flow on more
targets. Results recorded before the update stay readable in **Execution**; they show the task
name without a call ID. Flows that read results by task name, filter on one call, or set
per-occurrence settings need further edits:
[Migrate Saved Flows](../developer-guide/workflow/task-calls.md#migrate-saved-flows).

## Save and Test the Workflow

1. Select **Save Flow** for a new workflow. For an existing workflow, select **Edit**, make the
   change, then select **Save**.
2. Confirm that **Flow saved successfully!** appears without a save error.
3. Select **Execute** and review **Flow Name**, **Username**, **Chip ID**, and **Tags**.
4. Confirm that no other run should use the chip. A workflow reserves the entire chip until all
   its steps finish.
5. Select **Execute**, then open **Execution** to follow task order, status, parameters, and
   results.

Use a small target and non-destructive task settings for the first run. Confirm the resulting task
order and effective parameters before adding a schedule or expanding the targets.

How this works: [Workflow Authoring Quickstart](../developer-guide/workflow/quickstart.md).

## Organize Your Workflows

The **Workflow** page lists each workflow under its creator and, inside that space, under the
folders you choose. Filing happens in the editor's **Explorer** panel, which shows one creator's
space as `folder/name.py`; the selector at its top switches to another creator, and **Open in
editor** on a creator's folder on the **Workflow** page opens the editor on that space. Moving a
workflow changes only where it is listed: its name, source file, schedules, and running
executions are untouched.

- **Move a workflow**: drag its row onto a folder, or onto the empty area below the tree for the
  top of the space; or right-click it and pick a folder from **Move … to**. Dragging a folder
  moves everything in it.
- **Make a folder**: select the folder button at the top of the Explorer, or right-click a
  folder and choose **New folder**, then type its name. The folder stays in the Explorer until
  you move a workflow into it or reload.
- **Rename a folder**: right-click it and choose **Rename folder**, or press F2 on it. Every
  workflow under it follows.
- **Set the folder while saving**: the **Folder** property takes a path such as `daily/t1`;
  `/` nests, and every level it names is created.

Workflows stay in their creator's space. Moving needs project edit permission, like saving.
