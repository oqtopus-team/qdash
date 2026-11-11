# Run Your First Calibration

Use the guide on **Home** to create a chip, run a calibration, and inspect its result on a Fake
deployment without hardware. For hardware-specific steps, see
[On a Qubex Deployment](#on-a-qubex-deployment).

## Before You Start

- QDash is running and you have signed in, as described in [Setup](./setup.md). On a fresh
  deployment, sign in as the initial administrator, who owns the default project that QDash
  creates for that account.
- You are an Editor or Owner of the active project; see
  [Choose a Project Role](./projects-and-data-sharing.md#choose-a-project-role).
- The deployment can store chip configuration. On a Fake deployment set up from the example
  `.env`, this is already in place; the **Create Chip** dialog blocks creation when it is not, as
  [Fake backend](./setup/fake-backend.md#create-a-chip) describes. On a Qubex deployment, place
  the configuration tree as described in [Qubex backend](./setup/qubex-backend.md).

## Start the Guide

1. Select **Home** in the sidebar.
2. Start the guide:
   - When the project has no chips, select **Create a chip** under **First calibration**.
   - Otherwise, select **First calibration guide** in the Home header, choose an existing chip or
     **Create a new chip**, and select **Start**.

If the guide cannot load the deployment or its chips, select **Try again**. Fake deployments offer
only chips matching the 64-qubit virtual device. If that device is unavailable, ask an administrator
to check the API configuration.

## Follow the Guide

Follow each callout to perform an action, or select **Next** to continue an explanation. You can
still use the rest of the page. The guide never saves a flow or starts a run without your action.

### Prepare a Chip

If you chose an existing chip, continue to [Review and Run](#review-and-run).

1. In the **Create Chip** dialog, enter a **Chip ID**.
2. Select **Create Chip**.

QDash creates the [virtual chip configuration](./setup/fake-backend.md#create-a-chip) and opens
**New Flow** with the **Fake Backend Calibration** template and the new chip selected.

### Review and Run

1. Next to the code editor, read **What this flow runs**: the tasks in run order and the MUX
   targets that the code declares. A first run can use the template unchanged.
2. Keep the suggested flow name, or enter another with letters, digits, and underscores.
3. Select **Save Flow**. The saved flow opens in the flow editor. **New Flow** never replaces an
   existing flow; if the name was taken in the meantime, enter another one and save again.
4. Select **Execute** once it is highlighted, check the chip ID in the confirmation, and select
   **Execute** to start the run.

A failed save or a run that does not start leaves you in the editor with your changes.

### Follow Progress

The run opens on **Execution**. The callout shows the completed task count while you wait.

When the run fails or is cancelled, the guide stays on this step and offers **Open the run** and
**Run again**. Open the run, or filter **Task Results** by status as described in
[Find a Result](./reviewing-results.md#find-a-result), to read the failed task's message. If the
services themselves stop responding, see [Operations](./operations.md#resolve-common-failures).

### Inspect a Result

When the run finishes, the callout points at a completed result, such as the **CheckT1** node of
the execution flow. Select it to open its preview, or open a result from the guide or from **Task
Results**. The callouts then explain the result's graph and its **Output Parameters**. Close the
preview to continue.

### Open the Chip Overview

Open the chip on **Chip**. Each tile shows the latest result of the selected task for one qubit;
choose another task to compare. Opening the overview finishes the guide, and Home shows **First
calibration complete** with links to the result and the overview.

## On a Qubex Deployment

The guide follows the same five steps on a Qubex deployment, with these differences:

- **Create Chip** also offers **Qubex configuration** options when a configuration tree is
  mounted: copy the wiring from an existing system, or start from a backend template. A new
  template has empty wiring and box entries; complete its hardware settings on **Config** before
  you run, as
  [Create the Configuration of a New Chip](./setup/qubex-backend.md#create-the-configuration-of-a-new-chip)
  describes. If you use a configuration repository, publish the completed files through **Config**;
  deployments without a repository use the local configuration.
- After you choose or create the chip, the guide stays on Home under **Hardware readiness**. It
  shows whether QDash found the configuration directory and the chip's wiring file, and asks you
  to confirm that the wiring and device parameters match the connected hardware. QDash cannot
  check the instruments themselves. The guide links to **New Flow** and to the run only after you
  confirm.
- In **New Flow**, choose the template for the chip under **TEMPLATE** before reviewing it.

## Pause and Resume the Guide

The strip under the top bar shows the current step. Select **Exit guide** or close a callout to
pause. On **Home**, select:

- **Resume** to continue from the recorded step.
- **Start over** to discard the guide.

The guide is kept in this browser for your account and the active project. A chip, flow, or run
that finishes after you switch project, pause, or start over is not added to the guide. The guide
checks each step against the chip, flow, and run that QDash recorded, so deleting one of them
returns the guide to the step that needs it.

## Continue After the First Run

[Running Calibrations](./running-calibrations.md) covers running saved workflows and single tasks
on other targets. [What the Fake Backend Runs](./setup/fake-backend.md#what-the-fake-backend-runs)
lists the tasks the template runs and how to change its targets. Use the
[Application Tour](./application-tour.md) to find the other pages of QDash.
