# Projects and Data Sharing

A project holds a team's chips, calibration values, workflows, results, and discussions.

## Active Project

Use the project selector to switch projects. Confirm the project and chip before running a
calibration or changing shared data. Every new account starts with its own default project.

## Choose a Project Role

| Role | Access |
| --- | --- |
| Viewer | Read results, download data, and join discussions |
| Editor | Viewer access plus calibration runs and operational changes |
| Owner | Editor access plus membership, settings, and deletion |

Each project has one Owner. Transfer ownership before that person leaves; the previous Owner
becomes an Editor. A system Admin still needs project membership to read calibration data.

## Create a Project

A system administrator creates projects and assigns owners from **Admin**.

## Manage Members

As the project owner:

1. Open **Settings → Project** in the intended project.
2. Under **Project Members**, enter an existing username, choose Viewer or Editor, and select
   **Add Member**.
3. Change or remove their access when needed.

![Adding a project member](/images/guides/add-project-member.gif)

Deleting a project removes its project records and cannot be undone through the UI.

## Share Results

Share a result link with someone who belongs to the same project. Accepted calibration values
are shared within that project and chip. Removing a member revokes access but preserves their
records. See [handing off a result](./reviewing-results.md#share-and-hand-off-a-result).

## Programmatic Access

Select the project in a [client profile](../reference/clients/python.md#connect-to-a-deployment).
There is no normal operation for moving data between projects; create or import it in the
intended project.
