# Dashboards

Use **Dashboards** to arrange metric maps, the results of your own metric scripts, and notes on
one page, keep that arrangement, and share it with the other members of your project.

**Overview** shows every configured metric for one chip in a fixed order. A dashboard shows only
the panels you add, in the layout you choose, so a team can agree on one view for a recurring
question such as "what is the median ZX90 fidelity of each coupling over the last two weeks" or
"which couplers are close to a Type1A collision after this cool-down".

**Dashboards** has two tabs. **Dashboards** lists the dashboards you own and those shared with
the project. **Scripts** lists metric scripts: Python files that compute one value per qubit or
per coupling for a **Metric script** panel. Writing a script is covered in
[Metric Scripts](./metric-scripts.md); this page covers dashboards and their panels.

## Create a Dashboard

Project editors and owners can create dashboards; viewers can open the dashboards shared with
them.

1. Open **Dashboards** and select **New dashboard**.
2. Enter a name and an optional description.
3. Under **Start from**, choose **Blank dashboard** or the **Frequency Collision Map** template.
   The template adds a how-to note, a qubit frequency map, and the Type0A, Type0B, Type1A,
   Type3A, Type1C, and Type2C collision checks. Its collision panels use the project's shared
   **Frequency collision checks** script; when the project has none yet, QDash creates it and
   shares it with the project. The dashboard is yours: later changes to the template do not
   alter it.
4. Choose **Private** to keep the dashboard to yourself or **Shared with project** to show it to
   every project member. You can change this later.
5. Choose the **Default chip**. Viewers can switch to another chip while they look at the
   dashboard without changing the saved default.
6. Select **Create dashboard**. The new dashboard opens; select **Edit** to add, remove, or
   reconfigure panels.

Change the name, description, visibility, or default chip later under **Dashboard settings**.

## Add Panels

In edit mode, select **Add panel**, choose the **Panel type**, and give the panel a title.

| Panel type | Shows | Settings |
| --- | --- | --- |
| **Qubit metric** | One qubit metric on the chip topology, with the same colour scale as **Overview** | Metric, **Value selection** (Latest, Best, or Average) |
| **Coupling metric** | One coupling metric on the chip topology | Metric, **Value selection** |
| **Metric script** | One metric of a saved metric script as a map or a table | **Script**, **Metric**, **Period**, **Parameters**, **View**, **Direction**, **Pair distance** |
| **Markdown note** | Free text, for example the purpose of the dashboard or the decision rule the team applies | Content |

For a **Metric script** panel:

1. Choose the **Script**. The list shows the scripts you can see that have a valid revision.
2. Choose the **Metric**: each metric the script defines.
3. Set the **Period**. **Last days** always shows the most recent number of days, measured when
   the panel loads; **Fixed range** shows the same start and end every time.
4. Adjust **Parameters** if the metric has any. Only values that differ from the default are
   kept.
5. Choose **Map** or **Table** under **View**. For a metric computed per coupling, choose the
   **Direction** to draw and the **Pair distance**: **1** for neighbouring qubits, **2** for
   qubits two steps apart, among the distances the metric supports.
6. Select **Apply**.

Each panel sits on a 12-column grid. Use the panel menu to move it, make it wider or narrower,
taller or shorter, duplicate it, or remove it. On a narrow screen every panel spans the full width.

Changes stay local until you select **Save**; **Discard** returns to the saved layout and **Done**
leaves edit mode. The dashboard stores the layout, the chip, and the panel settings, not measured
values: every time someone opens it, the panels read the current data of the selected chip.

## Keep Panels on a Known Script Revision

Every save of a metric script creates a numbered revision, shown as **r1**, **r2**, and so on.
A **Metric script** panel is pinned to the revision that was current when you added it, so
nobody's edit to a script changes what your dashboard shows without your knowledge.

When the script has a newer valid revision, the panel shows **Newer revision rN available**. In
edit mode, select **Update to rN** on the panel, check the result, and **Save** the dashboard to
move the pin. A saved revision that a dashboard pins is kept even when the script has many later
revisions. A script keeps at most 50 revisions, so when dashboards pin 50 of them, saving new
code is refused until some panels are updated to a newer revision or removed.

## Read a Metric Script Panel

A map shows qubits on the chip layout. A metric computed per coupling is drawn on the edges
between qubits: a solid edge connects neighbouring qubits, a dashed edge qubits two steps apart.
Each direction of a pair is its own edge, because results such as a ZX90 gate fidelity belong to
a control and a target qubit. Switch between **Both**, **Forward** (from the lower to the higher
qubit number), and **Reverse** to show one direction at a time. The legend explains the colours
and counts the targets in each.

A grey or empty target has no value. Select it to see why: no data in the period, too few
observations for the script's threshold, or an error in the script, with the line it occurred on.
The other targets are still valid when one target fails.

Select a qubit or an edge to open its details: the value and label, the **Checks** the script
reported (for example the number of samples, the minimum and the maximum), **Defaults and
estimates** it used, and the **Inputs** it read, with the task and time of each measurement. Use
**Copy all** to paste these into a note or a forum post.

The **Table** view lists every target with its value, status, sample count and label; sort it by
any column and copy it as CSV. The panel footer shows the period that was actually used and the
parameter values in effect.

## Share and Reuse

A dashboard set to **Shared with project** appears under **Shared with project** on
**Dashboards** for every member of the project. Members can open it, switch its chip for
themselves, and use **Copy link** to send the page to a colleague, who needs access to the same
project to open it.

A shared dashboard can only use scripts that are also shared with the project; QDash refuses to
save one that uses a private script. Share the script first from its **Settings** in the script
editor.

Only the owner and project owners can edit, re-share, or delete a dashboard. Any editor can
select **Duplicate** to get a private copy to change independently; the copy keeps the pinned
script revisions. Dashboards and scripts belong to the project in which they were created and are
not visible from other projects; see [Projects and Data Sharing](./projects-and-data-sharing.md).

How this works: [Custom Dashboards architecture](../developer-guide/architecture/custom-dashboards.md).
