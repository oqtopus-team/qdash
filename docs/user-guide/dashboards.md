# Dashboards

Use **Dashboards** to arrange metric maps, the results of your own metric scripts, and notes on
one page, keep that arrangement, and share it with the other members of your project.

**Overview** shows every configured metric for one chip in a fixed order. A dashboard shows only
the panels you add, in the layout you choose, so a team can agree on one view for a recurring
question such as "what is the median ZX90 fidelity of each coupling over the last two weeks" or
"which couplers are close to a Type1A collision after this cool-down".

**Dashboards** has two tabs. **Dashboards** lists the dashboards you own and those shared with
the project. **Scripts** lists metric scripts: Python files that compute one value per qubit or
per coupling that a metric panel can show. Writing a script is covered in
[Metric Scripts](./metric-scripts.md); this page covers dashboards and their panels.

## Create a Dashboard with the Agent

Project editors and owners can create dashboards; viewers can open the dashboards shared with
them. The quickest start is to describe the dashboard to the [Agent](./ai-chat.md) and review
the draft it proposes.

1. Open **Dashboards** and select **Create with Agent**. A new, unsaved dashboard opens with the
   **Ask Agent** sidebar beside it. Nothing is sent until you ask.
2. Describe what you need, or pick a suggested request such as "Build a frequency collision map
   from the starter template" or "Show the median ZX90 fidelity per coupling over the last 14
   days". The Agent reads the available metrics, scripts, and templates and proposes a draft as
   a diff in the chat.
3. Select **Apply to draft**. The panels appear on the page, and the name the Agent chose
   appears in the name field; change it if you like. When the draft starts from a template, the
   page shows the template's panels as a preview, with data from the selected chip, and copies
   them into the dashboard when you save. If the project does not have the template's shared
   metric script yet, the page says that **Save** also adds it, shared with the project; until
   then the script panels run the template's code without storing anything. **Discard** in the
   chat leaves the draft as it was.
4. Adjust the draft yourself if needed: **Add panel**, the panel menus, and the **Chip** work as
   in [edit mode](#add-panels). Ask for further changes; each proposal is a diff against the
   draft as it is now, including your own edits.
5. Select **Save**. QDash creates the dashboard as **Private** and opens it. Share it later from
   the dashboard's actions menu.

The draft lives only in your browser until you save it. If QDash refuses it, for example because
a panel names a script revision that does not exist, the error is shown and the draft stays so
you can fix it. To keep a metric the Agent computes, it first saves a metric script, which asks
for your approval; see [Write a Script with the Agent](./metric-scripts.md#write-a-script-with-the-agent).

## Create a Dashboard Yourself

1. Open **Dashboards** and select **New dashboard**.
2. Under **Start from**, keep the **Frequency Collision Map** template, which is preselected, or
   choose **Blank dashboard**. The template adds a qubit frequency map, the Type0A, Type0B,
   Type1A, Type3A, Type1C, and Type2C collision checks, ready to read on your chip, and a short
   note on reading their colours. Its collision panels use the project's shared **Frequency collision checks** script;
   when the project has none yet, QDash creates it and shares it with the project. The dashboard
   is yours: later changes to the template do not alter it. When the templates cannot be
   loaded, the dialog says so, offers **try again**, and selects **Blank dashboard**.
3. The **Name** follows the chosen template until you type your own.
4. Choose the **Chip**. The newest active chip is preselected. Viewers can switch to another
   chip while they look at the dashboard without changing the saved default.
5. Under **Sharing**, keep **Private** or choose **Shared with project** to show it to every
   project member. You can change this later.
6. Select **Add a description** to add an optional description.
7. Select **Create dashboard**. The new dashboard opens with its panels on the chosen chip;
   select **Edit** to add, remove, or reconfigure panels.

Change the name, description, sharing, or default chip later under **Dashboard settings**
in the dashboard's actions menu, next to **Edit**.

## Add Panels

In edit mode, select **Add panel** and choose **Metric** or **Note** under **Panel**. A note
holds Markdown text, for example the purpose of the dashboard or the decision rule the team
applies. A metric panel shows one metric on the chip topology or in a table:

1. Under **Show**, choose the metric. The list groups **Qubit metrics** and **Coupling metrics**,
   which read the latest calibration like **Overview**, and then each metric a saved script
   computes, under the script's name, with its unit and whether it is per qubit or per pair.
   Scripts without a valid revision are not listed; a private script is marked **(private)**.
   The full name of the chosen metric and its source appear below the list.
2. The **Title** follows the metric until you type your own.
3. For a qubit or coupling metric, choose the **Value selection**: **Latest**, **Best**, or
   **Average**.
4. For a script metric, set the **Period** and the **View**. **Last days** always shows the
   most recent number of days, measured when the panel loads; **Fixed range** shows the same
   start and end every time. For a metric computed per pair, choose the **Direction** to draw
   and the **Pair distance**: **1 hop** for neighbouring qubits, **2 hops** for qubits two
   steps apart, among the distances the metric supports.
5. Open **Advanced** to adjust the metric's **Parameters**, if it has any, and to see which
   script and revision the panel uses. Only parameter values that differ from the default are
   kept. The section opens by itself when the panel already has parameter values.
6. Select **Apply** (or **Add panel**).

Each panel sits on a 12-column grid. Use the panel menu to move it, make it wider or narrower,
taller or shorter, duplicate it, or remove it. On a narrow screen every panel spans the full width.

On your own dashboard, select **Edit with Agent** to open the **Ask Agent** sidebar with the dashboard,
the chip it shows, and its current panels, unsaved changes included. On a dashboard without
panels, **Ask Agent** comes first, next to **Add panel**. The Agent proposes a new panel list as a
diff; **Apply to draft** enters edit mode with the proposed panels, and nothing is stored until
you select **Save**. The Agent does not change sharing, and it keeps each panel's script
revision unless you ask it to move one.

Changes stay local until you select **Save**; **Discard** returns to the saved layout and **Done**
leaves edit mode. If someone else saved the dashboard after you selected **Edit**, **Save** fails
with a message to reload, and your changes stay on screen so you can note them before reloading. The dashboard stores the layout, the chip, and the panel settings, not measured
values: every time someone opens it, the panels read the current data of the selected chip.

## Keep Panels on a Known Script Revision

Every save of a metric script creates a numbered revision, shown as **r1**, **r2**, and so on.
A panel that shows a script metric is pinned to the revision that was current when you added
it, so nobody's edit to a script changes what your dashboard shows without your knowledge.

When the script has a newer valid revision, the panel shows **Update available**. In edit
mode, select **Use updated definition** on the panel, or in the panel's **Advanced** section,
which shows the pinned and the active revision numbers; check the result, then **Save** the
dashboard to move the pin. Nothing moves until you do. A saved revision that a dashboard pins
is kept even when the script has many later revisions. A script keeps at most 50 revisions, so
when dashboards pin 50 of them, saving new code is refused until some panels are updated to a
newer revision or removed.

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

A shared dashboard can only use scripts that are also shared with the project. When you select
**Share with project** and a panel uses a private script, QDash lists those scripts instead of
sharing: select **Open script settings** for a script you own and share it from its
**Settings** in the script editor, or ask the owner named in the list, or replace the panel.
QDash never shares a script on your behalf. The panel editor warns in the same way when you add
a private script's metric to a shared dashboard.

Only the owner and project owners can edit, re-share, or delete a dashboard; **Share with
project**, **Make private**, and **Delete dashboard** are in the dashboard's actions menu. Any
editor can select **Duplicate** to get a private copy to change independently; the copy keeps the
pinned script revisions. Dashboards and scripts belong to the project in which they were created and are
not visible from other projects; see [Projects and Data Sharing](./projects-and-data-sharing.md).

How this works: [Dashboards architecture](../developer-guide/architecture/dashboards.md).
