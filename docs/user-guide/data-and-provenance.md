# Calibration Data and Provenance

Use the data views to trace a chip-wide finding to the measurement that produced it.

## Choose a View

| Question | Open |
| --- | --- |
| Is the chip healthy? | **Overview** |
| How does one metric compare across targets? | **Metrics** |
| What is the latest result of a task? | **Chip** |
| How did parameters change? | **Analysis** |
| What produced a value? | **Lineage** |
| What happened in a run? | **Execution** or **Task Results** |

Check the project, chip, time range, cool-down, and coupling direction before comparing data.

## Scan Current State

Choose the [Overview scope](./overview.md#select-the-data-scope), then inspect coverage and
metrics. **Metrics** compares one parameter across targets.

## Inspect Measurements

On **Chip**, select a task, then a qubit or coupling. For a cross-run search, use **Task Results**.
Figures and raw data appear only when the task produced them.

## Follow Parameter History

Use **Analysis** to compare values over time. Open **Lineage** from a result, metric history,
or an execution's **Parameter changes** to see its producer, inputs, and dependent values.
**Full graph** expands its ancestry. After changing an input, re-run the tasks that produced
values derived from it.

## Modify Current Parameters

1. Open **Calibration DB → Modify parameters**.
2. Compare YAML candidates with current values.
3. Select and edit the values to import, review the changes, then confirm.
4. To remove a current value, use **Edit import value → Delete** and confirm.

Only permitted parameters appear. Calibration-derived frequencies may be excluded from seed
imports even when YAML contains them. Review each change before applying it.

How this works: [Calibration Data Lifecycle](../developer-guide/workflow/calibration-data-lifecycle.md).
