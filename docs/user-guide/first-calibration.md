# Run Your First Calibration

The first calibration guide on **Home** takes a project editor from a chip to an inspected result
in five steps: prepare a chip, review and run a workflow, follow its progress, inspect a result,
and open the chip overview. This page follows the guide on a Fake deployment and notes where a
Qubex deployment differs.

## Before You Start

The guide needs a running deployment and a signed-in member who may run calibrations:

- QDash is running and you have signed in, as described in [Setup](./setup.md). On a fresh
  deployment, sign in as the initial administrator.
- You are an Editor or Owner of the active project. The guide is shown only to project editors.
  The initial administrator owns the default project that QDash creates for that account; any
  other member needs the role described in
  [Projects and Data Sharing](./projects-and-data-sharing.md#choose-a-project-role).
- On a Qubex deployment, the configuration tree is in place as described in
  [Qubex backend](./setup/qubex-backend.md). A Fake deployment needs no preparation.

## Start the Guide

Sign-in opens **Execution**. Select **Home** in the sidebar, then start the guide:

- When the project has no chips, select **Create a chip** under **First calibration**.
- Otherwise select **First calibration guide** in the Home header, choose an existing chip or
  **Create a new chip**, and select **Start**.

The guide offers a chip only after it has checked how the deployment runs calibrations and which
chips the project has. If that check fails, select **Try again** on Home. A Fake deployment
whose API does not offer the virtual device offers no chip and says what an administrator must
check.

## Follow the Guide

On every page the guide passes through, a callout points at the control to use next and gives one
instruction, such as **Name the chip**, **Save the flow**, or **Start the run**. A callout that
asks for an action moves on only when you take it: creating the chip, saving the flow, starting
the run, or opening a result. Callouts that explain the template, the flow name, or a result's
graph and values have **Next**. The rest of the page stays usable while a callout is shown.

1. **Prepare a chip.** The guide opens the **Create Chip** dialog, or uses the chip you chose.
   When creating a chip, enter a **Chip ID** and select **Create Chip**. On a Fake deployment the guide offers only
   chips with the 64 qubits of the virtual device; [Fake backend](./setup/fake-backend.md#create-a-chip)
   describes what the dialog creates. On a Qubex deployment the guide also explains the **Qubex
   configuration** options, which are available only when a configuration tree is mounted: they
   create a directory named after the chip ID by copying the wiring from an existing system or
   starting from a backend template. Push the new files from the **Config** page before you run a
   calibration.
2. **Review and run.** On a Fake deployment, creating the chip opens **New Flow** on the **Fake
   Backend Calibration** template for that chip. On a Qubex deployment, confirm the chip's
   hardware readiness first, then choose the template. Next to the code editor, **What this flow
   runs** lists the tasks in order and the MUX targets that the code in the editor declares; a
   first run can use the template unchanged. **New Flow** suggests a free flow name and never
   replaces an existing flow; if the name is taken by then, enter another one. Select
   **Save Flow**: the saved flow opens in the flow editor with **Execute** highlighted once the
   flow can run. Select **Execute** and confirm. The guide never saves or starts a run by itself,
   and a failed save or run leaves you in the editor with your changes.
3. **Follow progress.** A run you confirm in the guide opens on **Execution**. While it runs, the
   callout shows how many tasks have finished and waits; it has no **Next**. A failed or cancelled
   run stays on this step with **Run again** and **Open the run**.
4. **Inspect a result.** When the run finishes, the callout points at a completed result, such as
   the **CheckT1** node of the execution flow. You can also open one from the guide or from
   **Task Results**. The callout then explains the result's graph and **Output Parameters**. The
   guide stays on this step until you finish the explanation or close the result.
5. **Chip overview.** Open the chip on **Chip** to see the calibrated values; this finishes the
   guide.

On a Qubex deployment, as soon as the chip is chosen and before the guide links to **New Flow** or
the run, it shows whether QDash found the configuration directory and the chip's wiring file, and
asks you to confirm that the wiring and device parameters match the connected hardware. QDash
cannot check the instruments themselves.

When a run fails, select **Open the run**, or filter **Task Results** by status as described in
[Find a Result](./reviewing-results.md#find-a-result), to read the failed task's message. If the services
themselves stop responding, see [Operations](./operations.md#resolve-common-failures).

## Pause and Resume the Guide

On other pages, a strip under the top bar shows the current step and its next action. **Exit
guide** in the strip, or the close button of a callout, pauses the guide and hides both. Home then
offers **Resume**, which continues at the step the recorded chip, flow, and run point to; **Start
over** discards the guide.

The guide is kept in this browser for your account and the active project. A chip, save, or run
that finishes after you switch project is not added to either project's guide, and one that
finishes after you pause or restart the guide does not move you to another page. Each step is
checked against the chip, flow, and run that QDash recorded, so a deleted chip, flow, or run
returns the guide to the step that needs it. Links to the former chip setup tour open the guide.

## Continue After the First Run

[Running Calibrations](./running-calibrations.md) covers running saved workflows and individual
tasks with other targets, and [Fake backend](./setup/fake-backend.md#what-the-fake-backend-runs)
lists the tasks the template runs. Use the [Application Tour](./application-tour.md) to find the
other pages of QDash.
