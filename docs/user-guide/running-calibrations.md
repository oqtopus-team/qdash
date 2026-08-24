# Running Calibrations

QDash supports reusable project workflows and a task workbench for one-off calibration runs.

## Choose a Run Mode

Use a workflow when tasks must run as a repeatable graph, on a schedule, or with dependencies. Use
the Tasks workbench when you need to run one calibration task against selected targets and inspect
the result immediately.

Both modes require an active chip and project edit permission. The selected project determines the
workflow files, calibration state, execution history, and generated artifacts used by the run.

## Run a Workflow

1. Open **Workflow** and select an existing project workflow, or create one.
2. Review the workflow source and properties. Save any edits before running it.
3. Select the chip and other run options required by the workflow.
4. Start the run. QDash registers the flow with the deployment service and Prefect.
5. Open **Execution** to monitor status and task progress.

The workflow editor also supports schedules. Manage schedules in QDash so the project workflow
metadata and Prefect deployment remain aligned. The Prefect dashboard is useful for operational
inspection, but it is not the primary editor for QDash workflows.

## Run One Task

1. Open **Tasks** and choose a calibration task.
2. Select the chip and the qubit or coupling targets accepted by that task.
3. Review the resolved input and run parameters. Reload current values if calibration state has
   changed since the task was selected.
4. Submit the task and follow the resulting execution.
5. Inspect input, output, run parameters, figures, and raw data from the result.

The workbench resolves current calibration values for convenience, but the displayed values
should still be reviewed before submission.

## Monitor Executions

The **Execution** page lists workflow runs and their current status. Open an execution to inspect
its task topology and select a node for parameters, output, and artifacts. The topology view can
show task dependencies, use a grid layout, and expand to full screen for larger runs.

Use **Task Duration Breakdown** from the execution area to compare task timing across selected
executions. Duration analysis requires timestamped task results.

Cancelling a running execution requests cancellation through Prefect. QDash then synchronizes the
execution and task statuses and releases the execution lock. A cancellation can take time to reach
the worker if a task is inside an operation that cannot be interrupted immediately.

## Inspect Results

Use **Task Results** to filter across executions by chip, execution, task, and status. Open a result
to inspect:

- execution and target context;
- input, output, and run parameters;
- figures and downloadable raw data;
- user notes and linked issues;
- re-execution and exclusion controls when available.

Use the Execution detail when the dependency graph matters. Use Task Results when you know the
task, status, or target you want to investigate.

## Files and Artifacts

Workflow definitions and project configuration are managed from **Files**. The editor tracks
unsaved changes and provides project Git operations. Save before requesting an AI review or
creating a pull request. Pulling can replace the working copy, so resolve or discard unsaved edits
first.

Execution figures and raw data are stored under the configured calibration data path and remain
associated with the project, chip, execution, and task result. See
[Calibration Data Sharing](./calibration-data-sharing.md) for storage and migration behavior.
