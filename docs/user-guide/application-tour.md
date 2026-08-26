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

See [Projects and Sharing](./projects-and-sharing.md) for membership and role details.

## Overview

| Page | Purpose |
| --- | --- |
| **Home** | Start common work and review active executions, failed tasks, and recent notifications. |
| **Dashboard** | Scan all configured chip metrics, coverage, distributions, and scoped notes. |
| **Metrics** | Inspect one metric across qubits or couplings and compare its history. |
| **Chip** | Browse calibration tasks and the latest results on the chip topology. |
| **Analysis** | Plot and compare chip parameters over a selected time range. |
| **AI Chat** | Ask questions using the [project-aware Copilot interface](./copilot.md). |

Use **Dashboard** for broad health checks, **Metrics** for a parameter-focused investigation, and
**Chip** when the calibration task or physical target is the starting point.

## Operate

| Page | Purpose |
| --- | --- |
| **Workflow** | Create, edit, schedule, and run project workflow definitions. |
| **Execution** | Monitor workflow runs, topology, statuses, timing, and task output. |
| **Task Results** | Search task outcomes across executions and focus on failures. |
| **Tasks** | Run an individual calibration task with resolved parameters. |
| **Cryo** | Manage cryostats, cool-downs, and wiring context. |
| **Import** | Compare and import initial calibration parameters from Qubex YAML. |

Workflow, Tasks, and some external operational links are shown only to members with edit
permission. See [Running Calibrations](./running-calibrations.md) for the end-to-end flow.

## Collaborate

| Page | Purpose |
| --- | --- |
| **Inbox** | Review mentions, replies, and system notifications. |
| **Issues** | Track and discuss a problem attached to a task result. |
| **Forum** | Hold project-wide discussions that are not tied to one result. |
| **Knowledge** | Reuse curated cases derived from resolved issues. |
| **AI Reviews** | Inspect bulk AI review runs and their target-level findings. |
| **Task Knowledge** | Read task physics, expected results, failure patterns, and analysis guidance. |

See [Reviewing and Sharing Results](./reviewing-results.md) for how these records relate.

## Manage

| Page | Purpose |
| --- | --- |
| **Files** | Edit project workflow and configuration files and use the Git integration. |
| **Settings** | Change appearance, account settings, active project, and project membership. |
| **Admin** | Manage system users and administrative settings. |

The Files and Admin pages are permission-gated. File saves, Git operations, imports, workflow
runs, and administrative actions change shared state; confirm the active project before using
them.

## External Tools

The bottom of the sidebar links to this documentation, the Prefect dashboard, and the interactive
API documentation. Prefect and API documentation links are available to project editors. Use the
QDash UI or API for workflow changes so QDash project metadata remains synchronized with Prefect.
