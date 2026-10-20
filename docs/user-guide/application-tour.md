# Application Tour

QDash groups project-scoped calibration work into Overview, Operate, Collaborate, and Manage
sections in the application sidebar.

## Project Context

Most data in QDash belongs to the active project. Select the intended project before inspecting
or changing calibration data. Project roles control what is visible:

- Viewers can inspect project data and participate where their permissions allow.
- Editors can create and run workflows, edit project files, and change calibration data.
- Project owners manage membership and project settings.
- System administrators manage users and system-wide settings from **Admin**.

See [Projects and Data Sharing](./projects-and-data-sharing.md) for membership and role details.

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
| **Calibration DB** | Compare and import initial calibration parameters from Qubex YAML. | [Calibration Data and Provenance](./data-and-provenance.md#import-initial-parameters) |

Workflow, Tasks, and some external operational links are shown only to members with edit
permission. See [Running Calibrations](./running-calibrations.md) for the end-to-end flow.

## Collaborate

| Page | Purpose | Guide |
| --- | --- | --- |
| **Inbox** | Review mentions, replies, and system notifications. | [Reviewing and Sharing Results](./reviewing-results.md#follow-notifications) |
| **Forum** | Hold project-wide discussions that are not tied to one result. | [Reviewing and Sharing Results](./reviewing-results.md#start-a-discussion) |
| **Knowledge** | Maintain task background and expert-labeled examples. | [Reviewing and Sharing Results](./reviewing-results.md#reuse-the-finding) |

See [Reviewing and Sharing Results](./reviewing-results.md) for how these records relate.

## Manage

**Under construction** marks an implemented page whose operating guidance still needs a product
decision or review. The marker does not mean that the feature is unavailable.

| Page | Purpose | Guide |
| --- | --- | --- |
| **Config** | Edit Qubex configuration files and synchronize their repository. | **Under construction** |
| **Settings** | Change appearance, account settings, active project, and project membership. | **Under construction** |
| **Admin** | Manage system users and administrative settings. | **Under construction** |

The Config and Admin pages are permission-gated. File saves, Git operations, imports, workflow
runs, and administrative actions change shared state; confirm the active project before using
them.

## External Tools

The bottom of the sidebar links to this documentation, the Prefect dashboard, and the interactive
API documentation. Prefect and API documentation links are available to project editors. Use the
QDash UI or API for workflow changes so QDash project metadata remains synchronized with Prefect.
