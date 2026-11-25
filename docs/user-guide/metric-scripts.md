# Metric Scripts

A metric script computes values from calibration data for a [dashboard](./dashboards.md) map,
table, or time-series chart.

## Create a Script

1. Open **Dashboards → Scripts → New script**.
2. Choose a name, template, and **Private** or **Shared with project**, then select **Create script**.
3. In the editor, change the code, **Validate**, then **Preview** it on a chip and period.
4. Inspect the values and any errors, then select **Save** to create a revision.

Editors and owners can create scripts or use **Copy to my scripts** on a shared script. Viewers
can preview shared scripts. Validation checks declarations; preview also runs the metric functions.

## Write a Metric

Decorate each function you want to show with `@metric`:

```python
from qdash_metrics import metric


@metric(title="T2 echo / T1", unit="dimensionless")
def coherence_ratio(target, ctx):
    t2 = ctx.data["t2_echo"][target].latest()
    t1 = ctx.data["t1"][target].latest()
    return t2 / t1
```

`target` is a qubit ID string. Return a number in the declared unit, a compatible unit-bearing
value, `None` for missing data, or `CellResult` with details. Exceptions affect that target only.
Renaming the function changes the metric's identity; update panels using the old name.

## Read Data

| Expression | Result |
| --- | --- |
| `ctx.data["t1"][target].latest()` | Latest completed, non-excluded measurement in the period |
| `ctx.data["t1"][target].history()` | Measurements in the period, oldest first |
| `ctx.topology.neighbors(target)` | Coupled qubits |
| `ctx.start`, `ctx.end` | Selected period in UTC |

History items expose `value`, `timestamp`, `task_id`, `execution_id`, and `excluded`.
Use `include_excluded=True` to include excluded observations. Explicit `start` and `end` values
need timezones. Latest measurements are not necessarily current operational calibration values.

### Units

Values already include the configured unit and scale. Convert with `.to("MHz")` and use
`.magnitude` for a number; do not apply the scale again.

### Pairs Are Directed

Declare `target="pair"` for directed pairs. The argument exposes `source`, `target`, and `hops`.
`0>1` and `1>0` are different measurements. Set `hops=(1,)` for neighbours, `(2,)` for two hops,
or `(1, 2)` for both. `ctx.coupling_strength(a, b)` alone tries both directions.

### Chip Layout

`ctx.topology.offset(target, row=-1)` finds a qubit one row above, or returns `None` at the edge.
The chip must have a topology for previews and panels.

## Show Counts and Missing Data

Import `CellResult` from `qdash_metrics`. Use
`CellResult(value, assessment={"count": count, "label": "median"})` to explain aggregates.
The assessment can also contain `checks` as name/value pairs and `estimates` as sentences.
Return `CellResult(None, assessment=...)` to explain missing data.

## Chart a Trend Over Time

Start with **ZX90 fidelity trend**, or declare `result="series"` and return `SeriesResult`
containing `SeriesPoint` values. Choose up to 16 targets in preview or the panel. Points need
increasing timezone-aware times inside the period; `None` creates a gap.

`time_bins(ctx.start, ctx.end, "day")` creates UTC-day bins; `"week"` starts weeks on Monday.
Use each bin's `select(history)` to aggregate observations. A series supports up to 400 days,
1,024 points per target, and 8,192 points overall. It uses **Chart**, not map or table.

## Parameters, Colours and Legends

Declare adjustable values with `parameters={"threshold": Parameter(default=1.0, min=0)}` and
read them from `ctx.params`. Import `Parameter` from `qdash_metrics`. Defaults determine the
input type; `choices`, `min`, and `max` constrain it.

`CellResult(value, color="#2563eb")` sets a target colour. `Legend.categorical` explains explicit
colours; `Legend.continuous` maps increasing value stops to colours. Import these helpers from
`qdash_metrics`, or keep the automatic scale.

## Periods

**Last days** moves with the current time. **Fixed range** keeps the same dates. The panel footer
shows the actual period.

## Save and the Active Revision

Each changed save creates a revision. Valid code becomes active; invalid code is saved with
diagnostics while the previous valid revision stays active. A script needs a valid revision
before it can be added to a panel. Existing panels keep their [pinned revision](./dashboards.md#keep-panels-on-a-known-script-revision).

## Limits

Imports are limited to `numpy`, `scipy`, `math`, `statistics`, and `qdash_metrics`. Scripts cannot
read files, start programs, use `exec`/`eval`, or access the network. These controls are for trusted
project members, not a security boundary for untrusted code.

Runs default to 60 seconds and a memory limit; operators can [adjust them](./setup.md#limit-metric-script-runs).
A history read covers at most 400 days and 5,000 measurements; a run allows 2,000 reads.
Longer history spans are clipped with a warning. Narrow the period when limits are exceeded.
Scripts are limited to 256 KiB and captured output to 16 KiB.

## Templates

| Template | Use |
| --- | --- |
| **Getting started** | Ratios, neighbouring frequencies, and aggregates |
| **Median ZX90 fidelity** | Median fidelity and sample count per directed coupling |
| **ZX90 fidelity trend** | Daily or weekly medians for selected couplings |
| **Frequency collision checks** | Qubex-compatible collision screening |

<a id="median-zx90-fidelity-per-coupling"></a>
<a id="daily-or-weekly-zx90-trend"></a>

Create a script from the template, choose a chip and period under **Preview**, and inspect sample
counts and missing values. Then **Save** and add its metric to a dashboard. Collision estimates,
including Type2C's detuning window, are screening aids rather than calibrated tolerances.

## Write a Script with the Agent

Describe the calculation in **Ask Agent**. Review its diff, select **Apply to editor**, then
**Validate**, **Preview**, and **Save**. The assistant sees unsaved editor code; applying a draft
does not save it.

How this works: [Metric Scripts architecture](../developer-guide/architecture/metric-scripts.md).
