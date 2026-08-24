# Calibration Data and Provenance

QDash provides complementary views for current chip state, metric history, raw task results, and
parameter lineage.

## Select the Right View

| Question | Page |
| --- | --- |
| Is the chip broadly healthy? | Dashboard |
| How does one metric compare across targets? | Metrics |
| What is the latest result for a task on each target? | Chip |
| How did parameters change over time? | Analysis or Provenance |
| What exactly happened in one run? | Execution or Task Results |

All views use the active project and selected chip. Time range, cool-down, target direction, and
latest/best/average selection can change which record is shown; include those filters when sharing
an observation with another user.

## Dashboard and Metrics

**Dashboard** presents all configured metrics with coverage, heatmaps, distributions, and scoped
notes. **Metrics** focuses on a selected metric and provides qubit or coupling history, parameter
details, notes, issues, report export, and data export where available.

For directional coupling data, verify the displayed direction before comparing values. For time
ranges, distinguish the latest value from best or average aggregation.

## Chip and Task Artifacts

**Chip** organizes calibration task results on the device topology. Select a task, then a qubit or
coupling to open its details and history. Multi-select actions can request AI review or download
figures for the displayed results.

Task-result pages expose the stored parameters and artifacts for one measurement. Figure JSON and
NetCDF raw data are downloadable when that task produced them.

## Analysis

**Analysis** plots selected chip parameters over time. Use it to compare trends and identify a
time window for deeper inspection. The available parameters come from the configured metric and
calibration data; an empty chart can mean the selected chip, target, parameter, or time range has
no matching records.

## Provenance

**Data Provenance** tracks calibration parameter history and lineage using W3C PROV-DM concepts.
Use it to answer which task result produced a value, which inputs contributed to it, and which
downstream parameters may depend on it. The page can also derive recalibration recommendations
from affected lineage and pass a task list to the workflow editor.

Provenance is project-scoped. Values created before project-scoped calibration was introduced are
available only after the corresponding migration has resolved their project, chip, and artifact
context. See [Calibration Data Sharing](./calibration-data-sharing.md) for the current layout.

## Import Initial Parameters

**Import** compares Qubex YAML values with QDash calibration state before importing initial
parameters. Review the comparison rather than treating the file as an unconditional overwrite.
Imported values become part of the calibration history and provenance context.
