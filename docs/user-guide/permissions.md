# Roles and Permissions

QDash authorizes requests with two independent layers: a system role on the account and a project role on each membership.

## Role Layers

| Layer | Roles | Controls |
| --- | --- | --- |
| System role (`SystemRole`) | User, Admin | Account administration, project creation, and platform operations. |
| Project role (`ProjectRole`) | Viewer, Editor, Owner | Access to one project's data and operations. |

Project roles map to coarse permissions: Viewer has read, Editor has read and write, and Owner has read, write, and admin. New members default to Viewer.

A system Admin has no automatic access to project data. Project permissions come only from membership or ownership, so an Admin who is not a member of a project receives `403` on its project-scoped endpoints. Admins can add themselves as a member through the Admin page or API.

## System Capabilities

| Capability | User | Admin |
| --- | --- | --- |
| Sign in, edit own profile, change own password | Yes | Yes |
| Create users, bulk import users | No | Yes |
| Reset another user's password | No | Yes |
| Change a user's system role, delete users | No | Yes |
| Create projects | No | Yes |
| Delete projects they do not own, manage members of any project | No | Yes |
| Transfer project ownership | No | Yes |
| Open the Admin page | No | Yes |
| Run system updates, reload configuration caches | No | Yes |

## Project Capabilities

| Capability | Viewer | Editor | Owner |
| --- | --- | --- | --- |
| View project details and the member list | Yes | Yes | Yes |
| View chips, metrics, executions, task results, provenance, and notes | Yes | Yes | Yes |
| Preview spectroscopy re-analysis (no data is written) | Yes | Yes | Yes |
| Create, edit, and delete chips and chip notes | No | Yes | Yes |
| Run flows, calibration pipelines, and quick-run tasks | No | Yes | Yes |
| Save, schedule, and delete flows and schedules | No | Yes | Yes |
| Cancel executions | No | Yes | Yes |
| Re-execute own task results | No | Yes | Yes |
| Exclude any task result in the project | No | Yes | Yes |
| Edit calibration parameters and import seed parameters | No | Yes | Yes |
| Write and delete qubit, coupling, and task notes | No | Yes | Yes |
| Add comments to qubit and coupling notes | No | Yes | Yes |
| Create evaluation runs and set verdicts | No | Yes | Yes |
| Create agent sessions, submit actions, commit and apply candidates | No | Yes | Yes |
| Create, edit, and delete cryostats, cooldowns, and wiring checkpoints | No | Yes | Yes |
| Edit project name and description | No | No | Yes |
| Invite, change, and remove members | No | No | Yes |
| Delete the project | No | No | Yes |

Editors and Owners can edit or delete only their own note comments. A system Admin can edit or delete any comment, but still needs Editor or Owner access to the project.

## Forum Permissions

The [forum](./reviewing-results.md) combines project roles with authorship of a post.

| Capability | Viewer | Editor | Owner | Post author |
| --- | --- | --- | --- | --- |
| Read posts, replies, categories, and labels | Yes | Yes | Yes | Yes |
| Create posts and replies, upload images | Yes | Yes | Yes | Yes |
| Edit thread metadata (title, category, labels, target, cooldown, assignee, status) | No | Yes | Yes | Yes |
| Edit the content of a thread or reply | No | No | Yes | Yes |
| Delete a thread or reply | No | No | Yes | Yes |
| Close or reopen a thread | No | Yes | Yes | Yes |
| Create, rename, and delete categories | No | No | Yes | No |
| Create, rename, and delete labels | No | Yes | Yes | No |

Thread metadata belongs to the root thread, so replies have content only. Editors can change metadata but not the content of other members' posts, and they can also create, rename, and delete labels. Because status is thread metadata, Editors can also close or reopen a thread by editing it; the dedicated close and reopen endpoints accept only the author and Owner.

The Post author column applies to the author's own posts and adds to the author's project role, so a Viewer can still edit and delete their own posts. Authors must remain project members to reach the forum. Resolved threads no longer accept replies.

## UI Visibility

The sidebar hides entries the current user cannot use:

- Workflow, Tasks, and Config appear only for Editors and Owners, as do the Prefect and API Docs links.
- Admin appears only for system Admins.

Hiding a control is a convenience, not enforcement: project-scoped API endpoints check the project role on each request.

## Implementation Files

| File | Purpose |
| --- | --- |
| `src/qdash/datamodel/user.py` | System roles |
| `src/qdash/datamodel/project.py` | Project roles and permission mapping |
| `src/qdash/api/lib/project.py` | Project context dependencies for viewer, editor, and owner checks |
| `src/qdash/api/routers/admin.py` | Admin-only endpoints |
| `src/qdash/api/services/forum_service.py` | Forum author and role rules |
| `ui/src/components/layout/navigation.ts` | Sidebar visibility |
