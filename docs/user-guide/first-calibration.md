# Run Your First Calibration

The first calibration guide on **Home** takes a project editor from a chip to an inspected result
in five steps: **Prepare a chip**, **Review and run**, **Follow progress**, **Inspect a result**,
and **Chip overview**. This page follows the guide on a Fake deployment, which contacts no
hardware. [On a Qubex Deployment](#on-a-qubex-deployment) lists what changes when QDash controls
hardware.

## Before You Start

- QDash is running and you have signed in, as described in [Setup](./setup.md). On a fresh
  deployment, sign in as the initial administrator, who owns the default project that QDash
  creates for that account.
- You are an Editor or Owner of the active project. The guide is shown only to project editors;
  another member needs the role described in
  [Choose a Project Role](./projects-and-data-sharing.md#choose-a-project-role).
- The deployment can store chip configuration. On a Fake deployment set up from the example
  `.env`, this is already in place; the **Create Chip** dialog blocks creation when it is not, as
  [Fake backend](./setup/fake-backend.md#create-a-chip) describes. On a Qubex deployment, place
  the configuration tree as described in [Qubex backend](./setup/qubex-backend.md).

## Start the Guide

1. Select **Home** in the sidebar. Sign-in opens **Execution**, not Home.
2. Start the guide:
   - When the project has no chips, select **Create a chip** under **First calibration**.
   - Otherwise, select **First calibration guide** in the Home header, choose an existing chip or
     **Create a new chip**, and select **Start**.

The guide offers a chip only after it has checked how the deployment runs calibrations and which
chips the project has. If that check fails, select **Try again**. On a Fake deployment, the guide
offers only chips with the 64 qubits of the virtual device; when the API does not offer the
virtual device, the guide offers no chip and asks you to have an administrator check the API
configuration.

## Follow the Guide

On each page, a callout points at the next control and names the action, such as **Name the
chip**, **Save the flow**, or **Start the run**. A callout that asks for an action moves on when
you take it. A callout that explains the page has **Next**. The rest of the page stays usable while
a callout is shown, and the guide never saves a flow or starts a run by itself.

### Prepare a Chip

If you chose an existing chip, continue to [Review and Run](#review-and-run).

1. In the **Create Chip** dialog, enter a **Chip ID**.
2. Select **Create Chip**.

QDash configures the virtual device for the new chip; [Create a Chip](./setup/fake-backend.md#create-a-chip)
lists what the dialog creates. **New Flow** then opens on the **Fake Backend Calibration**
template with the new chip selected.

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

The run opens on **Execution**. While it runs, the callout shows how many tasks have finished and
waits for the run to end; it has no **Next**.

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
  mounted: copy the wiring from an existing system, or start from a backend template. Complete the
  new chip's files on **Config** before you run, as
  [Create the Configuration of a New Chip](./setup/qubex-backend.md#create-the-configuration-of-a-new-chip)
  describes.
- After you choose or create the chip, the guide stays on Home under **Hardware readiness**. It
  shows whether QDash found the configuration directory and the chip's wiring file, and asks you
  to confirm that the wiring and device parameters match the connected hardware. QDash cannot
  check the instruments themselves. The guide links to **New Flow** and to the run only after you
  confirm.
- In **New Flow**, choose the template for the chip under **TEMPLATE** before reviewing it.

## Pause and Resume the Guide

On pages other than Home, a strip under the top bar shows the current step and its next action.
**Exit guide** in the strip, or the close button of a callout, pauses the guide and hides both.
Home then marks the guide **Paused** and offers:

- **Resume**, which continues at the step that the recorded chip, flow, and run point to.
- **Start over**, which discards the guide.

The guide is kept in this browser for your account and the active project. A chip, flow, or run
that finishes after you switch project, pause, or start over is not added to the guide. The guide
checks each step against the chip, flow, and run that QDash recorded, so deleting one of them
returns the guide to the step that needs it. Links to the former chip setup tour open the guide.

## Continue After the First Run

[Running Calibrations](./running-calibrations.md) covers running saved workflows and single tasks
on other targets. [What the Fake Backend Runs](./setup/fake-backend.md#what-the-fake-backend-runs)
lists the tasks the template runs and how to change its targets. Use the
[Application Tour](./application-tour.md) to find the other pages of QDash.
