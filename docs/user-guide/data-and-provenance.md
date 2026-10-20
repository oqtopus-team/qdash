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
| Which result produced a value? | **Data Provenance** |
| What happened in one run? | **Execution** or **Task Results** |

The active project, chip, time range, cool-down, target direction, and value selection determine
what these pages show. Include that scope when sharing an observation.

## Scan Current State

1. Open **Dashboard** and select a chip.
2. Set the time range or cool-down and choose the latest, best, or average value selection.
3. Review coverage and distributions, then select a metric or target that needs investigation.

Open **Metrics** when one parameter across many targets is the focus. For coupling data, confirm
the displayed direction before comparing values.

## Inspect Measurements

Open **Chip** and select a task to see its latest results on the topology. Select a qubit or
coupling to open its history and artifacts. Use **Task Results** to search across executions by
chip, task, target, or status.

Figures and raw data are available only when the selected task produced them.

## Follow Parameter History

Open **Analysis** to compare selected parameters over time. If a chart is empty, broaden the time
range and confirm the chip, target, and parameter selections.

Open **Data Provenance** to trace a current value back to the task result and inputs that produced
it. Use the affected lineage to identify downstream values that may need recalibration.

## Import Initial Parameters

Use **Calibration DB** to review current values or import permitted values from Qubex YAML:

1. Open **Calibration DB** and select **Import from YAML**.
2. Select a permitted YAML source and compare its values with the current database.
3. Select the parameters to import and edit them if needed.
4. Review the proposed changes, then confirm the import.

The import view shows only parameters the deployment permits. Frequency values produced by
calibration experiments can be excluded from seed import even when a YAML file contains them.
Treat the comparison as a review, not as an unconditional overwrite.

How this works: [Calibration Data Lifecycle](../developer-guide/workflow/calibration-data-lifecycle.md).
