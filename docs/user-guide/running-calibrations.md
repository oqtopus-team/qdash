# Running Calibrations

Run a saved workflow from **Workflow**, or one task from **Tasks**. Both require project edit
permission. Confirm the active project and chip before starting.

## Choose a Run Mode

| Goal | Start from |
| --- | --- |
| Run or schedule a task sequence | **Workflow** |
| Run one measurement | **Tasks** |
| Repeat earlier work | Its execution or task result |

## Run a Workflow

1. Open **Workflow** and choose a flow, or [create one](./creating-workflows.md).
2. Save any source changes before selecting **Execute**.
3. Review the chip and **Calibration targets**. Leave them unchanged to use saved defaults,
   or enter MUX IDs, qubit IDs, or directed **Coupling pairs** when offered.
4. Confirm **Execute**, then follow the run on **Execution**.

Target edits apply only to this run. **Use code defaults** clears them. Coupling pairs use
`control-target`, such as `0-1`; reversing a pair changes the operation. Manual-round workflows
use their saved rounds and do not accept target overrides.

## Schedule a Workflow

Save and test the workflow with its intended default targets first; schedules use those defaults.

1. Open the saved workflow, select **Properties**, and find **Schedule**.
2. Choose **Cron** for recurring runs or **One-time** for a single future run. Times are in
   **Asia/Tokyo (JST)**. For example, `0 2 * * *` means daily at 02:00 JST.
3. For a recurring run, check **Enable schedule immediately** only when ready.
4. Select **Add Cron Schedule** or **Create One-time Schedule** and confirm it appears under
   **Active Schedules**.

Use the recurring schedule's toggle to pause it, or **Delete schedule** to remove it.
These actions do not cancel a run that has already started; inspect that run on **Execution**.

## Run One Task

1. Open **Tasks** and select a task, **Chip**, and **Qubit or coupling**.
2. Select **Reload** to check hardware availability and load inputs.
3. Review **Input parameter overrides** and **Run parameters**.
4. Enable **Reconfigure hardware first** if the saved configuration must be applied first.
5. Enable **Update calibration values** only if successful outputs should become current values.
6. Select **Run task** and follow **Results**.

An occupied hardware resource blocks the run. See [Task Parameters](./task-parameters.md) for
input resolution and exploratory runs.

## Monitor a Run

On **Execution**, open a run or task to inspect status, progress, parameters, and artifacts.
Cancellation requests can take time to stop an uninterruptible hardware operation.

**Group sessions** collects runs under their calibration objective or agent session. Expand a
row to inspect its runs. **Open** and **Closed** describe whether an objective accepts more work,
not whether it succeeded. Runs started without an objective get an **Automatic** session.

Switch to **Calibration sessions** to find objectives. Their pages show runs, recorded search
progress, and an **Audit** with **Export JSON**. Recommendations are recorded statements;
they do not prove which values are currently on hardware. Missing evidence is **Not recorded**.

For agent sessions, use **Open session graph** and follow
[Agent Calibration](./agent-calibration.md#follow-a-session-on-the-execution-page).

## Inspect a Result

Use **Task Results** to search by chip, task, execution, target, or status. Open a result for
its figures, raw data, and notes. See [Reviewing and Sharing Results](./reviewing-results.md).

## Edit Workflow Configuration

Use **Config** for Qubex files. Save local changes before pulling or creating a pull request;
pulling can replace the working copy.
