# Run Your First Calibration

Use the guide on **Home** to create a chip, run a workflow, and inspect a result.

## Before You Start

Sign in to a deployment set up with the [Fake backend](./setup/fake-backend.md), with Editor or
Owner access to the project. Hardware deployments need the additional checks below.

## Start the Guide

On **Home**, select **Create a chip** under **First calibration**. If the project already has
chips, select **First calibration guide**, choose a chip or **Create a new chip**, then **Start**.

![Starting the first-calibration guide](/images/guides/first-calibration-start.gif)

## Follow the Guide

### Prepare a Chip

Enter a **Chip ID** and select **Create Chip**. QDash opens **New Flow** with the
**Fake Backend Calibration** template. Skip this step if you chose an existing chip.

### Review and Run

1. Read **What this flow runs** beside the editor. The Fake template can run unchanged.
2. Enter a unique flow name using letters, digits, and underscores.
3. Select **Save Flow**.
4. Select **Execute**, check the chip in the confirmation, then select **Execute** again.

![Reviewing the flow and its targets, MUX 0-3 of the chip](/images/guides/first-calibration-review-flow.gif)

![Executing the saved flow on the chip and MUX 0-3](/images/guides/first-calibration-execute.gif)

### Follow Progress

The guide opens **Execution** and shows progress. If the run fails or is cancelled, select
**Open the run** to inspect the message before **Run again**. See [Operations](./operations.md)
if the services are unavailable.

![Following the run on Execution while tasks complete](/images/guides/first-calibration-follow-progress.gif)

### Inspect a Result

When the run finishes, open the highlighted completed task.

![Opening the CheckT1 result from the execution flow](/images/guides/first-calibration-open-result.gif)

Review its figure and **Output Parameters**.

![Reading the CheckT1 figure and its output parameters](/images/guides/first-calibration-read-result.gif)

Close the preview to continue.

![Closing the result preview](/images/guides/first-calibration-close-preview.gif)

### Open the Chip Overview

Open the chip on **Chip**. Each tile shows the latest result of the selected task.

![Opening the chip overview on Chip](/images/guides/first-calibration-chip-overview.gif)

This completes the guide; Home keeps links to the result and overview.

![Home after the guide, with links to the result and the chip overview](/images/guides/first-calibration-complete.gif)

## On a Qubex Deployment

Prepare the [Qubex configuration](./setup/qubex-backend.md) first. A chip created from a template
still needs its real wiring, boxes, and device settings filled in on **Config**.

At **Hardware readiness**, confirm that the configuration matches the connected hardware;
QDash checks files, not instruments. In **New Flow**, choose the appropriate hardware template
before reviewing and running it.

## Pause and Resume the Guide

Select **Exit guide** or close a callout to pause. On **Home**, select **Resume** to continue or
**Start over** to reset the guide. Progress is saved in this browser for your account and project.

<a id="continue-after-the-first-run"></a>

## Continue After the Guide

[Run another calibration](./running-calibrations.md), [create a workflow](./creating-workflows.md),
or [review and share results](./reviewing-results.md).
