# Dashboards

Use **Dashboards** to save and share a layout of metrics and notes. Use [Overview](./overview.md)
when you want all configured metrics without building a layout. Creating or editing dashboards
requires Editor or Owner access. Agent-assisted creation also needs [AI setup](./setup/ai.md).

## Create a Dashboard with the Agent

1. Select **Create with Agent** and describe the view you need.
2. Review the proposed diff and select **Apply to draft**.
3. Check the panels and chip, then select **Save**.

Nothing is stored until Save. The new dashboard is private. A template may also create a shared
metric script; the draft tells you before saving.

## Create a Dashboard Yourself

1. Select **New dashboard**.
2. Choose a template or **Blank dashboard**.
3. Set the **Name**, **Chip**, and **Sharing**.
4. Select **Create dashboard**, then **Edit** to change its panels.

The **Frequency Collision Map** template creates the project's shared collision script if needed.
Use **Dashboard settings** later to change the name, sharing, or default chip.

## Add Panels

1. In edit mode, select **Add panel**, then **Metric** or **Note**.
2. For a metric, choose **Show**, then its value selection or script period and view.
3. For a pair metric, check **Direction** and **Pair distance**. For a time series, enter up to
   16 qubits or directed pairs to chart.
4. Adjust script **Parameters** under **Advanced** if needed, then **Apply**.
5. Move or resize panels, then **Save**.

Drag a header to move a panel or a bottom corner to resize it. The panel menu offers the same
actions. **Discard** restores the saved layout. **Edit with Agent** can propose changes to the
draft; you still select **Save** to keep them.

The dashboard stores settings, not measurements: panels read current data whenever they load.

## Keep Panels on a Known Script Revision

A script panel stays on the revision used when it was added. When **Update available** appears,
select **Use updated definition** in edit mode, review the result, and **Save** to adopt it.
A script retains at most 50 revisions; if all are pinned, update or remove old panel pins before
saving more revisions.

## Read a Metric Script Panel

Select a qubit or directed edge to inspect its value, sample count, checks, estimates, and input
measurements. A grey target can mean missing data or an error; open it for the reason.
**Table** supports sorting and CSV copying. The footer shows the period and parameters used.

Pair directions are separate: **Forward** runs from lower to higher qubit number, **Reverse**
the opposite way. Solid edges join neighbours; dashed edges join targets two hops apart.

## Share and Reuse

Select **Share with project** to let every project member open the dashboard. Its scripts must
also be shared; QDash asks their owners to share them rather than doing so automatically.

Only the dashboard owner and project owners can edit or delete it. Any editor can **Duplicate**
it into a private copy. Share **Copy link** with members of the same project.

For custom calculations, see [Metric Scripts](./metric-scripts.md).
