# Projects and Data Sharing

QDash uses a project-based system to organize calibration data and enable collaboration between team members. This guide explains how to create projects, manage team access, and share calibration results.

## What is a Project?

A **Project** is a workspace that contains all your calibration data:

- Chips and their configurations
- Qubits and couplings
- Calibration executions and results
- Task definitions and parameters
- Backend configurations

Each piece of data in QDash belongs to exactly one project. When you create a new chip or run a calibration, it is automatically associated with your currently selected project.

## Getting Started

### Your Default Project

When you first register for QDash, a default project is automatically created for you. This project is named `{username}'s project` and you are set as the owner.

You can:

- Use this default project for all your work
- Create additional projects for different experiments or teams
- Invite collaborators to share your data

### Switching Projects

Use the project selector in the navigation bar to switch between projects you have access to. The currently active project determines which data you see and can modify.

## Creating a New Project

1. Click the project selector dropdown in the navigation bar
2. Select **"Create New Project"**
3. Enter a project name and optional description
4. Click **"Create"**

You automatically become the owner of any project you create.

## Team Roles and Permissions

QDash uses a simplified two-role permission model:

| Role       | Capabilities                                                                                       |
| ---------- | -------------------------------------------------------------------------------------------------- |
| **Viewer** | View all project data (chips, calibrations, results). Cannot modify anything.                      |
| **Owner**  | Full access: create/modify chips, run calibrations, invite/remove members, and delete the project. |

### Permission Summary

| Action                          | Viewer | Owner |
| ------------------------------- | :----: | :---: |
| View chips and calibration data |   ✅   |  ✅   |
| View execution history          |   ✅   |  ✅   |
| Download results                |   ✅   |  ✅   |
| Create/modify chips             |   ❌   |  ✅   |
| Run calibrations                |   ❌   |  ✅   |
| Update parameters               |   ❌   |  ✅   |
| Invite members                  |   ❌   |  ✅   |
| Remove members                  |   ❌   |  ✅   |
| Delete project                  |   ❌   |  ✅   |
| Transfer ownership              |   ❌   |  ✅   |

## Inviting Team Members

As a project owner, you can invite other QDash users to collaborate:

1. Open **Project Settings** from the project selector menu
2. Go to the **Members** tab
3. Click **"Invite Member"**
4. Enter the username of the person you want to invite
5. Click **"Send Invitation"**

The invited user will be added as a **Viewer** and see the project in their project list immediately.

### Managing Members

From the Members tab, owners can:

- **Remove members**: Revoke a user's access to the project
- **Transfer ownership**: Make another member the owner (you become a Viewer)

## Sharing Calibration Results

Once you have team members in your project, sharing is automatic:

1. **Run a calibration** in your project
2. **All members can view** the results
3. **Viewers** can see and download data
4. **Only the Owner** can modify and re-run calibrations

### Best Practices for Sharing

- Invite team members as **Viewers** so they can access results
- Keep **ownership** for active calibration work
- Create **separate projects** for different experiments or teams
- Use **descriptive project names** to keep things organized

## API Access

When accessing QDash programmatically, include the project context in your requests:

### Required Headers

```http
Authorization: Bearer <your-access-token>
X-Project-Id: <project-id>
```

### Example: List Chips in a Project

```bash
curl -X GET "https://your-qdash-instance/chips" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Project-Id: your-project-id"
```

## Workflow Integration

When running calibration workflows, specify the project context:

```python
from prefect import flow
from qdash.workflow.helpers import init_calibration, finish_calibration

@flow
def my_calibration(username, chip_id, qids, project_id):
    session = init_calibration(
        username=username,
        chip_id=chip_id,
        qids=qids,
        project_id=project_id,  # Associate with project
    )

    # ... run calibration tasks ...

    finish_calibration()
```

All results from this workflow will be stored in the specified project and visible to all project members.

## Project Settings

Access project settings from the project selector menu:

### General Settings

- **Project Name**: Display name for the project
- **Description**: Optional description of the project's purpose

### Danger Zone

- **Delete Project**: Permanently delete the project and all its data
  - Only the owner can delete a project
  - This action cannot be undone
  - All chips, calibrations, and results will be permanently removed

## Frequently Asked Questions

### Can I be a member of multiple projects?

Yes! You can belong to as many projects as you need. Use the project selector to switch between them.

### What happens to my data if I leave a project?

Your access is revoked, but the data remains in the project. You will no longer be able to view or modify it.

### Can I move data between projects?

Currently, data cannot be moved between projects. You would need to re-create the chip and re-run calibrations in the new project.

### What happens if the owner leaves?

Before leaving, the owner must transfer ownership to another member. A project cannot exist without an owner.

### Can I have multiple owners?

No, each project has exactly one owner. If you need another user to have write access, transfer ownership to them.

### How do I find my project ID?

Your project ID is shown in:

- Project Settings page
- URL when viewing project details
- API responses

