---
name: qdash-timeseries-diagnosis
description: Diagnose common-mode drift, shared periodicity, phase relationships, and possible environmental coupling across arbitrary QDash metrics and external sensor CSV logs. Use when calibration metrics oscillate, drift together, appear delayed or anti-correlated, or may be influenced by cryostat/environmental cycles.
---

# QDash Timeseries Diagnosis

Use this skill for evidence-based multi-timeseries investigation. Keep the
measurement schema and physical interpretation separate: the comparison tool
extracts mechanical evidence, while this skill guides conclusions and next
checks.

## Principles

- Do not hard-code metric names, targets, sensors, units, CSV columns, periods,
  or timezone assumptions.
- Preserve both raw and transformed results. A visually clean transformed plot
  must not replace the raw evidence.
- Correlation, shared periodicity, and phase alignment establish association,
  not causal direction.
- Consider a shared driver when multiple targets and an environmental sensor
  move together. The sensor itself may be a proxy for an unmeasured actuator,
  vibration, electrical noise, magnetic noise, or control cycle.
- Count observed cycles, not raw sample points, when judging periodic evidence.
- Resolve cooldown boundaries before interpreting drift or shared periodicity. Analyze each cooldown separately by default; never smooth, interpolate, correlate, or fit a period across a cooldown boundary unless an explicit cross-cooldown comparison is intended and clearly reported.

## Workflow

When a compared QDash series comes from a task-specific output, call `qdash_get_task_knowledge` for that task before assigning physical meaning to its values, expected behavior, or failure modes.

### 1. Fix the investigation scope

Record the reusable scope with `/qdash-investigation-setup` when multiple
comparison passes are expected. The JSON context accepts arbitrary QDash
series, CSV mappings, window/timezone, and transform defaults. Record:

- QDash profile and chip
- cooldown IDs and start/end boundaries from `qdash_list_cooldowns`
- any in-cooldown wiring events that overlap the window
- metrics and target IDs
- tags
- start/end timestamps
- timezone for every source
- expected cadence and units
- local CSV path, time column, value columns, and any row filters

For timestamps without an explicit zone, require a declared offset. Never infer
a timezone from the host machine.

### 2. Inspect source integrity

Before comparing, use `qdash_inspect_timeseries_csv` for local files whose
schema or time encoding is not already established. Use `qdash_list_cooldowns`
to split the requested window at cooldown boundaries, and inspect cooldown
wiring events when hardware conditions may have changed. Then:

- verify first/last timestamps and overlap
- check source point counts and cadence
- identify duplicate timestamps, missing intervals, and long gaps
- verify scale and offset conversions
- ensure labels are unique

Do not bridge long outages. Set `maxInterpolationGapMinutes` explicitly when the
default is unsuitable for the slowest source.

### 3. Establish a raw baseline

Call `qdash_compare_timeseries` first with:

- no smoothing
- no detrending
- no normalization
- no period search unless a period was specified independently

Report ranges, units, overlap, and raw correlation. Different units are fine for
correlation, but do not visually overlay incomparable scales without separate
axes or normalization.

### 4. Compare oscillatory components

When looking for common cycles, rerun with explicit settings such as:

- a smoothing window justified by source cadence
- `detrend: linear` when slow drift would dominate
- `normalize: zscore` for shape/phase comparison
- a period-search range chosen from prior evidence or a broad physically
  plausible interval

Report all transform settings with the result. Compare:

- full transformed correlation
- selected shared period
- per-series periodic explained fraction
- pairwise phase differences
- observed cycle count

A near-0° phase difference indicates in-phase periodic components. A near-180°
difference indicates anti-phase components. Intermediate phase may represent a
delay, but phase alone does not identify response direction.

### 5. Grade the evidence conservatively

Use qualitative language:

- **weak**: unstable period/phase, low explained fraction, or fewer than about
  three observed cycles
- **suggestive**: similar periods with plausible phase but short observation or
  substantial residual variation
- **strong association**: repeated common period and stable phase across
  multiple targets/sensors, with substantial explained fractions
- **causal evidence**: requires intervention, independently controlled input,
  repeated response, or evidence excluding plausible shared drivers

These are reasoning categories, not fixed acceptance thresholds. Explain which
facts support the chosen category.

### 6. Test alternatives

For apparent environmental or cryostat coupling, distinguish:

1. the measured sensor variable directly affecting the metric
2. a controller/refrigerator cycle affecting both
3. periodic measurement or scheduling artifacts
4. timestamp offset or resampling artifacts
5. target-local behavior coincidentally near the same frequency

Check additional targets in different control/readout groups and, when
available, actuator state, compressor/pulse-tube, vibration, rack temperature,
magnetic field, pressure, and control-system logs.

### 7. Recommend discriminating measurements

Prefer measurements that separate hypotheses:

- extend observation to cover at least 8–10 candidate cycles
- preserve the same cadence and synchronized clocks
- record actuator/controller state in addition to sensor output
- test multiple targets and control/readout groups
- perform a safe controlled setpoint or operating-state change when authorized
- compare lag/phase stability across independent runs

Do not initiate operational changes without an explicit plan and user
confirmation.

## Reporting template

Include:

1. sources and exact time window
2. timezone and unit conversions
3. raw-data integrity and overlap
4. transformation settings
5. raw/transformed correlations
6. shared period, phase, explained fraction, and observed cycles
7. strongest association statement
8. causal alternatives still open
9. next measurement that best discriminates those alternatives
