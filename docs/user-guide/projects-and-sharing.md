# Projects and Data Sharing

A QDash project is the access and storage boundary for chips, calibration state, workflows,
results, discussions, and files.

## Active Project

Use the project selector to switch between projects. The active project determines which chips,
workflows, executions, task results, notes, issues, and files QDash displays or changes. Confirm
it before starting a calibration or editing shared state.

Every new account receives a default project owned by that user. Users may also belong to other
projects and switch between them without copying data.

## Project Roles

| Role | Access |
| --- | --- |
| Viewer | Inspect project data and download available results. |
| Editor | Viewer access plus operational changes such as running workflows and editing calibration data. |
| Owner | Editor access plus project settings, membership, categories, ownership transfer, and deletion. |

Each project has one owner. Transfer ownership before the current owner leaves the project.

## Create and Configure Projects

A system administrator creates projects from **Admin** and assigns their owner. Give each project
a name that identifies the experiment, device, or team; add a description when the boundary is
not obvious.

Project owners manage an existing project from **Settings**. They can update its name and
description, invite existing QDash users, change member roles, remove members, and transfer
ownership. Assign viewer access for inspection and editor access only when the member needs to
change shared operational state.

Deleting a project removes its project-scoped records and is not reversible through the UI.
Review membership, chips, executions, and artifacts before confirming deletion.

## Share Results

Project members see calibration state and results produced in that project. A task result retains
the user and execution that produced it, while accepted calibration state is shared by project and
chip.

Before sharing a QDash link, confirm that the recipient belongs to the project. Removing a member
revokes access but does not delete records that member produced.

See [Calibration Data Sharing](./calibration-data-sharing.md) for execution snapshots, current
state, artifact paths, and migration behavior.

## Programmatic Access

Use the [QDash Client](./qdash-client.md) for scripts and agents. Select a saved profile and pass
the project through its configuration or client API. Low-level API integrations must send both a
bearer token and the project header:

```http
Authorization: Bearer <access-token>
X-Project-Id: <project-id>
```

The project ID is available in **Settings** and project API responses. Data cannot be moved
between projects as a normal UI operation; create or import it in the intended project instead.
