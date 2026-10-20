# Cryostats and Cool-downs

Use **Cryo** to record the cryostat, cool-down period, loaded chips, and wiring context associated
with calibration work.

## Understand the Records

| Record | Represents |
| --- | --- |
| Cryostat | One long-lived refrigerator, such as `K-101`. |
| Cool-down | One cooling and warm-up cycle for a cryostat, such as `2026-001`. |
| Loaded chip | A chip installed during that cool-down. |

A cryostat can have many cool-downs, and one cool-down can contain multiple chips. QDash uses the
active cool-down to associate new calibration data with its physical operating context.

## Register a Cryostat

1. Open **Cryo**.
2. Select **New cryostat**.
3. Enter the project-unique **Cryo ID**.
4. Add the name, manufacturer, model, and location that operators need to identify the hardware.
5. Select **Create cryostat**.

## Start a Cool-down

1. Find the cryostat and select **New cool-down**.
2. Enter a project-unique **Cooldown ID**.
3. Select **Create cool-down**.
4. Expand the new cool-down and use **Load chip…** to assign each installed chip.

The new record starts as active. New calibration data for a loaded chip is associated with that
cool-down. Unload a chip with the remove control beside its ID when it is no longer part of the
cycle.

To record an earlier cycle, create the cool-down, select its displayed date range, and edit
**Started** and **Ended**. Historical views use this period when you filter by that cool-down.

## Record Wiring

Expand a cool-down and enter the physical setup under **Wiring info**. Type `/` to insert a table,
image, heading, list, toggle, code block, or another supported block. Paste or drop an image when
a diagram communicates the setup more clearly. Changes save automatically; check the save status
before leaving the page.

Autosave keeps the current wiring but does not create a permanent history entry. When the wiring
changes during a cool-down:

1. Select **Save checkpoint** under **Wiring history**.
2. Describe the physical change.
3. Select **Save checkpoint** in the dialog.

Expand a checkpoint to inspect the saved snapshot, author, time, and description.

## End a Cool-down

Select **End now**, then confirm **End cool-down**, when the hardware begins warm-up or the cycle
otherwise finishes. New calibration data is no longer associated with that cool-down after it
ends.

## Filter Calibration Data

Select a cool-down from the filter on **Dashboard**, **Chip**, or another view that offers the
control. QDash applies the cool-down period and shows calibration data in that operating context.
For an active cool-down, the period ends at the current time.
