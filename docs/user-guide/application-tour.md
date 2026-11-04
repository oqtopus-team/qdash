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

When a project has no chips, Home highlights the **Setup tour** for project editors. After a chip
exists, the tour remains available as a compact Home action for replay. It opens the Chip page,
points to the creation action, and explains the chip ID and topology fields without creating data
until the form is submitted.

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

The bottom of the sidebar links to this documentation and, for project editors, to the Prefect
dashboard. Use the QDash UI or API for workflow changes so QDash project metadata remains
synchronized with Prefect. The interactive API documentation is not linked from the sidebar; it is
served at the API's `/docs` path, listed in [Setup](./setup.md#verify-the-installation).
