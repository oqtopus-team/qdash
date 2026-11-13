# Running Calibrations

Use **Workflow** for a repeatable sequence of tasks, or use **Tasks** to run one calibration task
against a selected qubit or coupling.

Both routes use the active project and chip. Confirm both before starting because a run can update
the calibration values used by later tasks.

## Choose a Run Mode

| Goal | Start from |
| --- | --- |
| Run a saved task graph or schedule | **Workflow** |
| Run one task and inspect its result immediately | **Tasks** |
| Repeat a previous run with selected values restored | The source execution or task result |

Running a workflow or task requires project edit permission.

## Run a Workflow

1. Open **Workflow** and select a workflow. Follow [Creating Workflows](./creating-workflows.md)
   first if you need to create or change one.
2. Select **Edit** before changing the source, then select **Save**.
3. Select **Execute**.
4. Review the flow name, username, chip, and tags in the confirmation dialog.
5. Under **Calibration targets**, review the defaults from the saved workflow. To change them
   for this run, select **MUX IDs** or **Qubit IDs** and enter IDs separated by commas or spaces.
   For MUX targets, use **Excluded qubit IDs** to omit individual qubits. For a two-qubit workflow
   that groups selected directed pairs automatically, enter **Coupling pairs** instead, as described below.
6. Confirm the run, then open **Execution** to follow its progress.

Leaving the target fields unchanged preserves the workflow's code settings. **Use code defaults**
discards target edits. An explicit change replaces the initial calibration targets throughout the
current flow run; later filtering steps still apply. The saved workflow and schedules are unchanged.
A workflow that targets all MUXes, or targets couplings without offering **Coupling pairs**, stops
with an error when you change its targets.

**Coupling pairs** replaces the MUX and qubit fields for automatic pair workflows, such as
**2Q Automatic Pairs**. Workflows that choose pairs from qubits or build opaque step lists in
helper functions do not offer it. Write each pair as `control-target`, for example `63-85`,
and separate pairs with commas, spaces, or new lines. Direction matters: `85-63` calibrates
the opposite direction, and each directed pair must exist on the run's chip. QDash groups only
these pairs using the chip's hardware constraints and the step's parallelism cap. Later filters
can remove pairs whose qubits no longer qualify.

**2Q Automatic Pairs** requires a saved `coupling_pairs` selection or a selection in **Execute**.
**2Q Manual Rounds** uses the rounds and targets saved in its source and offers no target override;
see [Write Two-Qubit Rounds](./manual-execution-rounds.md#write-two-qubit-rounds).

If targets depend on runtime calculations or differ within the workflow, the dialog cannot show a
single default. Leave the fields unchanged to use the code, or enter an explicit selection for the
run. Separate nested workflow runs retain their own targets.

Use the workflow schedule panel when the same flow must run automatically. Manage schedules in
QDash so the workflow and its Prefect deployment remain aligned.

## Run One Task

<!-- MEDIA PLACEHOLDER
File: /images/guides/task-workbench.gif
Start: Tasks with no task or target selected.
Sequence: Select a task, chip, and target; select Reload; then show resolved inputs and run options without starting hardware.
Alt: Task workbench ready to run one calibration task with resolved inputs and run options.
-->

1. Open **Tasks** and select a task.
2. Under **Setup**, select **Chip** and enter a **Qubit or coupling** such as `0` or `0-1`.
3. Select **Reload** to check hardware availability and load the current input values.
4. Review **Input parameter overrides** and **Run parameters**. Leave an input override blank to
   use the current calibration value.
5. Enable **Reconfigure hardware first** when the current calibration configuration must be
   applied before the task starts.
6. Enable **Update calibration values** only when successful outputs should become the current
   calibration values. The run is saved in task history either way.
7. Select **Run task** and follow the status in **Results**.

The run button stays disabled while another execution holds the same hardware or until **Reload**
has checked a changed target. See [Task Parameters](./task-parameters.md) before overriding inputs
or saving outputs.

## Monitor a Run

Open **Execution** to inspect a run's status, task topology, timing, parameters, output, and
artifacts. Select a task in the topology to open its details, or select a node in the execution
flow to preview its result in the same side panel that **Task Results** uses; open the full
result from there. While a run is in progress, its details and its page show how many tasks have
finished and which one is being measured, and the running task shows its measurement progress.

Cancelling a run sends a cancellation request to the worker. A task that is inside an operation
that cannot be interrupted can take time to stop.

The activity chart groups the chip's runs by status over **7d**, **30d** (default), or **90d**:

- **30d** and **90d** show one column per day.
- **7d** shows 28 six-hour periods starting at 00:00, 06:00, 12:00, and 18:00 in the
  deployment's time zone, including the current period.

Empty periods keep their columns. The chart labels how many executions a full block represents;
a partially filled block holds fewer. Hover over or focus a column for exact counts. Select it
to filter the list to that day, even in the six-hour view; select the same day again to clear
the filter.

## Inspect a Result

Open **Task Results** when you know the chip, execution, task, target, or status you want to find.
Open an item to inspect its effective parameters, figures, raw data, notes, and linked discussion.

Use an execution detail when the dependency graph matters. Use **Task Results** when one
measurement or failure is the focus. See [Reviewing and Sharing Results](./reviewing-results.md)
for the review workflow.

## Edit Workflow Configuration

Open **Config** to edit the active project's Qubex configuration files. Save local changes before
pulling or creating a pull request; pulling can replace the working copy.

Figures and raw data stay associated with the project, chip, execution, and task result that
produced them. See
[Share and Hand Off a Result](./reviewing-results.md#share-and-hand-off-a-result) before handing a
run over to another project member.
