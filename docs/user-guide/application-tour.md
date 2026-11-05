# Application Tour

QDash groups project-scoped calibration work into Overview, Operate, Collaborate, and Manage
sections in the application sidebar.

<!-- MEDIA PLACEHOLDER
File: /images/guides/application-sidebar.gif
Start: Home with a project selected and every sidebar section visible.
Sequence: Highlight each sidebar section, open the project selector, then return to Home.
Alt: QDash sidebar grouped into Overview, Operate, Collaborate, and Manage sections.
-->

## Project Context

Most data in QDash belongs to the active project. Select the intended project before inspecting
or changing calibration data. Project roles separate read access, operational changes, and project
management. See [Projects and Data Sharing](./projects-and-data-sharing.md#choose-a-project-role)
for the role to assign.

## Explore Calibration State

| Page | Purpose | Guide |
| --- | --- | --- |
| **Home** | Start common work and review active executions, failed tasks, and recent notifications. | This page |
| **Dashboard** | Scan all configured chip metrics, coverage, distributions, and scoped notes. | [Dashboard](./dashboard.md) |
| **Metrics** | Inspect one metric across qubits or couplings and compare its history. | [Calibration Data and Provenance](./data-and-provenance.md) |
| **Chip** | Browse calibration tasks and the latest results on the chip topology. | [Calibration Data and Provenance](./data-and-provenance.md) |
| **Analysis** | Plot and compare chip parameters over a selected time range. | [Calibration Data and Provenance](./data-and-provenance.md) |
| **AI Chat** | Ask questions using project calibration context. | [AI Chat](./ai-chat.md) |

Use **Dashboard** for broad health checks, **Metrics** for a parameter-focused investigation, and
**Chip** when the calibration task or physical target is the starting point.

## Run Your First Calibration

Project editors can follow a guided first calibration from **Home**, from chip to inspected
result. When the project has no chips, select **Create a chip** under **First calibration**.
Otherwise select **First calibration guide** in the Home header, choose an existing chip or
**Create a new chip**, and select **Start**.

On every page the guide passes through, a callout points at the control to use next and gives one
instruction, such as **Name the chip**, **Save the flow**, or **Start the run**. A callout that
asks for an action moves on only when you take it: creating the chip, saving the flow, starting
the run, or opening a result. Callouts that explain the template, the flow name, or a result's
graph and values have **Next**. The rest of the page stays usable while a callout is shown.

1. **Prepare a chip.** The guide opens the **Create Chip** dialog, or uses the chip you chose. On a
   Fake deployment it offers only chips with the 64 qubits of the virtual device.
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

The guide offers a chip only after it has checked how the deployment runs calibrations and which
chips the project has. If that check fails, select **Try again** on Home. A Fake deployment
whose API does not offer the virtual device offers no chip and says what an administrator must
check.

On a Qubex deployment, as soon as the chip is chosen and before the guide links to **New Flow** or
the run, it shows whether QDash found the configuration directory and the chip's wiring file, and
asks you to confirm that the wiring and device parameters match the connected hardware. QDash
cannot check the instruments themselves.

On other pages, a strip under the top bar shows the current step and its next action. **Exit
guide** in the strip, or the close button of a callout, pauses the guide and hides both. Home then
offers **Resume**, which continues at the step the recorded chip, flow, and run point to; **Start
over** discards the guide. The guide is
kept in this browser for your account and the active project. A chip, save, or run that finishes after
you switch project is not added to either project's guide, and one that finishes after you pause
or restart the guide does not move you to another page. Each step is checked against the
chip, flow, and run that QDash recorded, so a deleted chip, flow, or run returns the guide to the
step that needs it. Links to the former chip setup tour open the guide.

## Operate

| Page | Purpose | Guide |
| --- | --- | --- |
| **Workflow** | Create, edit, schedule, and run project workflow definitions. | [Running Calibrations](./running-calibrations.md) |
| **Execution** | Monitor workflow runs, topology, statuses, timing, and task output. | [Running Calibrations](./running-calibrations.md) |
| **Task Results** | Search task outcomes across executions and focus on failures. | [Reviewing and Sharing Results](./reviewing-results.md) |
| **AI Evaluations** | Request, inspect, and compare recorded evaluations of task results. | [AI Evaluations](./ai-evaluations.md) |
| **Tasks** | Run an individual calibration task with resolved parameters. | [Running Calibrations](./running-calibrations.md) |
| **Cryo** | Manage cryostats, cool-downs, and wiring context. | [Cryostats and Cool-downs](./cryostats-and-cool-downs.md) |
| **Calibration DB** | Review current values, modify YAML candidates, or delete an invalid current value. | [Calibration Data and Provenance](./data-and-provenance.md#modify-current-parameters) |

Workflow, Tasks, and some external operational links are shown only to members with edit
permission. See [Running Calibrations](./running-calibrations.md) for the end-to-end flow.

## Collaborate

| Page | Purpose | Guide |
| --- | --- | --- |
| **Forum** | Hold project-wide discussions that are not tied to one result. | [Reviewing and Sharing Results](./reviewing-results.md#start-a-discussion) |
| **Knowledge** | Maintain task background and expert-labeled examples. | [Reviewing and Sharing Results](./reviewing-results.md#reuse-the-finding) |

Mentions and replies arrive at the bell in the top bar, which shows the unread count. Select the
bell to preview the newest notifications, or **View all** to open **Inbox**. See
[Reviewing and Sharing Results](./reviewing-results.md#follow-notifications) for the notification
flow and the same page for how these records relate.

## Manage

The Config guide is under construction because its repository workflow still needs product-owner
review. The page is available to project editors.

| Page | Purpose | Guide |
| --- | --- | --- |
| **Config** | Edit Qubex configuration files and synchronize their repository. | **Under construction** |
| **Settings** | Change appearance, account settings, active project, and project membership. | [Authentication and Users](./authentication-and-users.md) and [Projects and Data Sharing](./projects-and-data-sharing.md) |
| **Admin** | Manage system users, projects, and administrative settings. | [Authentication and Users](./authentication-and-users.md#create-users) and [Projects and Data Sharing](./projects-and-data-sharing.md#create-a-project) |

The Config and Admin pages are permission-gated. File saves, Git operations, imports, workflow
runs, and administrative actions change shared state; confirm the active project before using
them.

## External Tools

The bottom of the sidebar links to this documentation, the Prefect dashboard, and the interactive
API documentation. Prefect and API documentation links are available to project editors. Use the
QDash UI or API for workflow changes so QDash project metadata remains synchronized with Prefect.
