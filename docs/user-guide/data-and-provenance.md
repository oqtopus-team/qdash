# Calibration Data and Provenance

Use QDash's data views to move from a chip-wide health check to one measurement and the values it
produced.

## Choose a View

| Question | Open |
| --- | --- |
| Is the chip broadly healthy? | **Dashboard** |
| How does one metric compare across targets? | **Metrics** |
| What is the latest result for a task on each target? | **Chip** |
| How did parameters change over time? | **Analysis** |
| Which result produced a value, and what depends on it? | **Lineage** on the result or metric |
| What happened in one run? | **Execution** or **Task Results** |

The active project, chip, time range, cool-down, target direction, and value selection determine
what these pages show. Include that scope when sharing an observation.

## Scan Current State

1. Open **Dashboard** and select a chip.
2. Set the time range or cool-down and choose the latest, best, or average value selection.
3. Review coverage and distributions, then select a metric or target that needs investigation.

Open **Metrics** when one parameter across many targets is the focus. For coupling data, confirm
the displayed direction before comparing values. Narrow the **Color range** above the topology when
an outlier flattens the other colors; the range is shared with **Dashboard** and described in
[Dashboard](./dashboard.md#scan-chip-health).

## Inspect Measurements

Open **Chip** and select a task to see its latest results on the topology. Select a qubit or
coupling to open its history and artifacts. Use **Task Results** to search across executions by
chip, task, target, or status.

Figures and raw data are available only when the selected task produced them.

## Follow Parameter History

Open **Analysis** to compare selected parameters over time. If a chart is empty, broaden the time
range and confirm the chip, target, and parameter selections.

Open **Lineage** on a task result, on an entry in a metric's history, or on a row of an
execution's **Parameter changes** to see which task produced the value, the current values that
task read, and the values derived from it. Manual edits and seed imports appear as the producer of
the values they wrote. After changing a value, re-run the tasks that produced the values derived
from it. **Full graph** shows every value the selected one derives from.

## Modify Current Parameters

Use **Calibration DB** to review current values, modify YAML candidates, or remove an invalid
current value:

1. Open **Calibration DB** and select **Modify parameters**.
2. Compare the YAML candidate values with the current database.
3. To change a value, select the parameters to import and edit them if needed.
4. Review the proposed changes, then confirm the import.
5. To remove a current value, select **Edit import value**, then select **Delete** and confirm the
   deletion.

The modification view shows only parameters the deployment permits. Frequency values produced by
calibration experiments can be excluded from seed import even when a YAML file contains them.
Treat the comparison as a review, not as an unconditional overwrite.

How this works: [Calibration Data Lifecycle](../developer-guide/workflow/calibration-data-lifecycle.md).
