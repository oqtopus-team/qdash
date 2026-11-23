# Cryostats and Cool-downs

Use **Cryo** to record where a chip is installed and the period when it is cold. Creating or
changing records requires Editor or Owner access.

## Understand the Records

A cryostat has one or more cool-downs; each cool-down can contain several chips. New calibration
data for a loaded chip is associated with its active cool-down.

## Register a Cryostat

1. Open **Cryo → New cryostat**.
2. Enter a project-unique **Cryo ID** and identifying details.
3. Select **Create cryostat**.

## Start a Cool-down

1. Select **New cool-down** on the cryostat.
2. Enter a project-unique **Cooldown ID** and select **Create cool-down**.
3. Expand the record and select **Load chip…** for each installed chip.

The record starts active. Use the remove control beside a chip to unload it. To record an older
cycle, select the date range and edit **Started** and **Ended**.

## Record Wiring

Edit **Wiring info** in the expanded cool-down. Changes save automatically; wait for the saved
status before leaving. To preserve a historical snapshot, select **Save checkpoint** under
**Wiring history**, describe the change, and confirm. Autosave alone does not create a checkpoint.

## End a Cool-down

Select **End now**, then **End cool-down**. New data is no longer associated with that cycle.

## Filter Calibration Data

Choose the cool-down on **Overview**, **Chip**, or another view that offers the filter. It uses
the recorded period; an active period ends at the current time.
