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
5. Confirm the run, then open **Execution** to follow its progress.

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
6. Enable **Save calibrated outputs to DB** only when successful outputs should become the current
   calibration values.
7. Select **Run task** and follow the status in **Results**.

The run button stays disabled while another execution holds the same hardware or until **Reload**
has checked a changed target. See [Task Parameters](./task-parameters.md) before overriding inputs
or saving outputs.

## Monitor a Run

Open **Execution** to inspect a run's status, task topology, timing, parameters, output, and
artifacts. Select a task in the topology to open its details.

Cancelling a run sends a cancellation request to the worker. A task that is inside an operation
that cannot be interrupted can take time to stop.

Use **Task Duration Breakdown** to compare task timing across executions. Only results with start
and end timestamps appear in the comparison.

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
