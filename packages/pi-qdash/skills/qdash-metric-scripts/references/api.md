# The `qdash_metrics` API

Metric scripts import from `qdash_metrics` only. The module exports `metric`, `CellResult`,
`Legend`, `Parameter`, `MissingData`, `Measurement`, `Quantity`, `QubitPair`, `SeriesPoint`,
`SeriesResult`, `TimeBin`, `time_bins`, `units` and `unit_name`. Nothing else is importable:
there is no `MetricContext`, `TimeBinSet` or options class.

## `@metric`

```python
from qdash_metrics import metric

@metric(title="T2 echo / T1", unit="dimensionless")
def coherence_ratio(target, ctx):
    return ctx.data["t2_echo"][target].latest() / ctx.data["t1"][target].latest()
```

`@metric(title, unit, target="qubit", hops=(1, 2), parameters=None, legend=None, result="scalar")`

| Argument | Meaning |
| --- | --- |
| `title` | Display name; must not be empty. |
| `unit` | Declared output unit, a pint unit name. `%`, `μs`, `""` and `a.u.` are accepted and normalized (`percent`, `us`, `dimensionless`, `au`). Use `dimensionless` for ratios. An unknown unit fails validation. |
| `target` | `"qubit"` (default) or `"pair"`. |
| `hops` | Pair metrics only: the pair distances the metric is meaningful for, a non-empty subset of `(1, 2)`. `hops=(1,)` evaluates coupled pairs only. |
| `parameters` | `{name: Parameter(...)}`; read the effective values from `ctx.params`. |
| `legend` | A `Legend`, or a function `legend(ctx) -> Legend` (for legends that depend on parameters). Scalar metrics only. |
| `result` | `"scalar"` (default): one value per target, shown as a map or table. `"series"`: a time series per selected target, shown as a chart; see [Series metrics](#series-metrics). |

The function name is the metric's ID (`metric_id` in previews and panels). Renaming the
function makes it a different metric; panels that used the old name stop validating. Helper
functions without the decorator are fine. One script may define several metrics.

The function is called as `function(target, ctx)` once per target:

- Qubit metrics: `target` is a normalized qubit ID string (`"5"`), once for every qubit of the
  chip topology.
- Pair metrics: `target` is a `QubitPair(source, target, hops)`, once for **each direction** of
  every pair whose coupling-graph distance is in `hops`, over the whole chip. `0>1` and `1>0`
  are separate cells. `QubitPair` has no string form; use `pair.source`, `pair.target`, or
  index `ctx.data` with the pair itself.
- Series metrics are called only for the targets the panel or preview selects, never for the
  whole chip.

## Return values

| Return | Cell |
| --- | --- |
| A number | `ok`, interpreted in the declared `unit`. |
| A pint `Quantity` | `ok`, converted to the declared unit (an incompatible unit is an error). |
| `None` | `empty`: the target was deliberately not evaluated. |
| `CellResult(value, color=None, assessment=None)` | `value` as above; `color` (`#RGB`/`#RRGGBB`) overrides the renderer's color; `assessment` adds details. |
| `CellResult(None, assessment={...})` | `missing`, shown together with the assessment (use it to say why, such as too few samples). |
| raises `MissingData` | `missing` with the exception message. `latest()` raises it when the period has no value. |
| raises anything else | `error` with the message, script line and function. Other cells are unaffected. |

Booleans, NaN and infinity are errors. `assessment` keys, all optional:

- `label`: a short string shown with the value (`"median of 14"`).
- `checks`: a list of `(label, value)` rows; values are numbers, strings or `None`.
- `estimates`: a list of strings (assumptions, fallbacks used).
- `count`: the number of observations behind the value. Set it for every aggregate.

## Series metrics

A `result="series"` metric returns `SeriesResult(points, label=None, assessment=None)` (or
`None` for `empty`) for each selected target. A panel or preview must select 1 to 16 targets:
qubit IDs (`"5"`) for a qubit metric or directed pairs (`"5>6"`, also written `"5-6"`) for a
pair metric. Each selected pair must be coupled at one of the metric's `hops`; otherwise the
evaluation fails with HTTP 422 before the script runs. Scalar metrics take no targets.

`SeriesPoint(timestamp, value=None, count=None, status=None, reason=None, start=None, end=None)`:

| Field | Rule |
| --- | --- |
| `timestamp` | Where the point is drawn: ISO 8601 string or datetime **with a timezone**, inside `[ctx.start, ctx.end]`. |
| `value` | A number in the declared unit, a Quantity (converted), or `None` for a gap. NaN, infinity and booleans are errors. |
| `count` | Observations behind the value: an int of at least 0, or `None`. A value cannot rest on `count=0`. |
| `status` | `"ok"` (has a value), `"no_data"` or `"insufficient"` (no value). Omitted: `ok` with a value, `no_data` with no value and no observations, `insufficient` with no value but observations. |
| `reason` | Short text shown with the point (up to 200 characters kept), such as why it is a gap. |
| `start`, `end` | The bin the point summarizes, both or neither, with `start <= timestamp <= end`, inside the period. |

Timestamps must be strictly increasing. The worker never sorts, resamples, interpolates,
clips or drops points: a series that breaks a rule makes that target an `error` cell naming
the point. A series whose points are all gaps is `missing` with a message counting them.
Caps: 1,024 points per series and 8,192 points over all selected targets (16 targets of 400
daily bins fit), and 6 MiB for all series cells as JSON, where a non-ASCII character costs 6 to
12 bytes; exceeding either total fails the whole evaluation (HTTP 422) rather than cutting
points or text. Keep reasons short, especially non-ASCII ones. A series cell keeps
its 100 most recent input references and sets `references_truncated` when it had more.

`time_bins(start, end, every="day" | "week")` returns `TimeBin` objects that tile the period
in UTC: days start at 00:00 UTC, weeks on Monday 00:00 UTC. The first and last bins are
clipped to the period (`partial` is true); `start` is inclusive and `end` exclusive, except
the last bin, which includes the period end. `bin.contains(moment)` and
`bin.select(measurements)` pick the observations of a bin. More than 1,024 bins is a
`ValueError`.

```python
import statistics

from qdash_metrics import Parameter, SeriesPoint, SeriesResult, metric, time_bins


@metric(
    title="T1 trend",
    unit="us",
    result="series",
    parameters={"interval": Parameter(default="day", choices=["day", "week"])},
)
def t1_trend(qubit, ctx):
    history = ctx.data["t1"][qubit].history()
    points = []
    for time_bin in time_bins(ctx.start, ctx.end, ctx.params["interval"]):
        values = [m.value.to("us").magnitude for m in time_bin.select(history)]
        points.append(
            SeriesPoint(
                time_bin.start,
                statistics.median(values) if values else None,
                count=len(values),
                start=time_bin.start,
                end=time_bin.end,
            )
        )
    return SeriesResult(points, label="median")
```

The chart draws one line per target in categorical colors, with the target and unit in the
legend and the bin, value and `n` in each tooltip; `n = 1` is labelled as one observation.
Gaps are not drawn and the line is not joined across them. Results are computed on every
view; a dashboard stores only the script revision and the panel settings.

## The context `ctx`

| Attribute | Meaning |
| --- | --- |
| `ctx.chip_id` | The evaluated chip. |
| `ctx.start`, `ctx.end` | The resolved period, UTC datetimes. |
| `ctx.params` | Read-only mapping of effective parameter values (defaults merged with the panel's or preview's values). |
| `ctx.data` | `ctx.data[metric_name][target]`: latest value and history (below). `"t1" in ctx.data` checks the catalog. |
| `ctx.topology` | Chip layout (below). |
| `ctx.coupling_strength(a, b)` | Measured coupling strength as a Quantity, or `None`. Tries both directions: the one deliberate undirected lookup. |
| `ctx.catalog` | `{"qubit_metrics": {...}, "coupling_metrics": {...}}` with title, unit, scale and description. |
| `ctx.references`, `ctx.record(metric, target, **details)` | Input provenance of the current cell. `ctx.data` records what it reads automatically; `record` adds an input by hand. |

### Data: `ctx.data[metric_name][target]`

`metric_name` must be a key of the QDash metrics catalog (`qdash_query`
`metric_script_catalog`, from `config/domain/metrics.yaml`); an unknown name raises
`KeyError` naming the catalog.

`target`:

- Qubit metrics: a qubit ID (`5`, `"5"`, `"Q05"` are the same). Indexing a qubit metric with a
  `QubitPair` is a `TypeError`; use `pair.source` or `pair.target`.
- Coupling metrics: a directed coupling ID `"0-1"` (or `"Q00-Q01"`) or a `QubitPair`, which
  maps to `f"{source}-{target}"`. **There is no reverse-direction fallback**: data recorded
  for `1-0` is not returned for `0-1`. Direction matters for CR, ZX90 and similar results.

`.latest()` returns a `Quantity`: the latest completed, non-excluded result **within the
period** (`[ctx.start, ctx.end]`), with the catalog unit and scale applied. There is no
fallback to a value outside the period; when the period holds none it raises `MissingData`.
It is the latest measurement, not necessarily the parameter currently in use on hardware.

`.history(start=None, end=None, include_excluded=False)` returns `list[Measurement]`, oldest
first: one record per task result that has this output parameter, with `start_at` in
`[start, end]` (inclusive). `start`/`end` default to the period; explicit bounds are ISO 8601
strings or datetimes and must include a timezone. Results excluded from statistics are skipped
unless `include_excluded=True`. Non-finite values are skipped. History is not filtered by task
status; `m.raw["status"]` has it if a metric needs to.

`Measurement` fields: `value` (Quantity), `timestamp` (UTC datetime), `task_id`,
`execution_id`, `excluded` (bool), `raw` (dict with `name`, `qid`, `status`, `error`,
`excluded_reason`).

### Units and scale

Values are pint Quantities. The catalog `scale` is applied exactly once, by the runtime; do
not multiply by it again.

- `latest()` always uses the catalog unit × scale.
- `history()` uses a record's own unit only when it is a physical unit with the same
  dimension as the catalog unit (for example a record in `us` for a catalog unit of `us`).
  Records without a unit, with `a.u.`, a dimensionless unit, or an incompatible unit are read
  as catalog unit × scale. A fidelity stored as `0.99` with catalog unit `%` and scale 100 is
  therefore `99 percent`.

Convert with `.to("MHz")`, `.to("percent")`, `.to("dimensionless")`; take `.magnitude` for a
float. Quantities of compatible units can be added and subtracted directly. A bare number
returned from a metric is taken to be in the declared unit.

### Topology: `ctx.topology`

- `positions[qid] -> (row, col)`; `qubits` (sorted IDs).
- `neighbors(qid)`: coupled qubits in numeric order (whole chip).
- `offset(qid, row=0, col=0)`: the qubit at that grid offset, or `None`. It does not follow
  couplings or skip holes. Raises `KeyError` for a qubit not on the chip.
- `pairs(hops=(1, 2))`: every directed `QubitPair` at those distances.
- `raw`: `{"qubits": {qid: {"row", "col"}}, "couplings": [[a, b], ...], "muxes": {...}}`.

The chip must have a topology; evaluation fails with HTTP 409 otherwise.

## Periods

A panel or preview gives the period; scripts do not choose it.

- `{"kind": "relative", "days": N}` (1 to 400, default 14) resolves to `[now - N days, now]`
  when the metric is evaluated, so a saved panel always shows the latest N days.
- `{"kind": "absolute", "start": ..., "end": ...}`: both ISO 8601 with a timezone, start on
  or before end. For a series metric it spans at most 400 days; a longer one is refused with
  HTTP 422 before the script runs.

`history()` with explicit bounds may read outside the panel period, but the broker clamps
any span longer than 400 days to the most recent 400 days of the request (the response's
`truncated` flag is set) and rejects a call that matches more than 5,000 records.

## Parameters

```python
Parameter(default, label="", min=None, max=None, step=None, unit="", choices=None)
```

The type of `default` decides the input kind: `int` → integer, `float` → number, `bool` →
boolean; `choices=[...]` with a string default → choice. Every parameter needs a valid
default. Numbers must be finite and within `min`/`max`; integers must be whole; booleans must
be real booleans; choices must be in the list. `step` is the input step (values are not
rounded); `unit` is only a label (no conversion). Unknown parameter names and invalid values
fail the evaluation (HTTP 422) and fail a dashboard save. Each panel stores its own values.

## Legends and colors

- `Legend.categorical([(color, label), ...])` explains colors; it does not assign them. Set
  each cell's color with `CellResult(color=...)`.
- `Legend.continuous([(value, color), ...])`: a color scale over the value, at least two
  stops, strictly increasing, **in the metric's declared unit**. The renderer interpolates.
- Without a color or a continuous legend the renderer picks a scale over the value range.

## Runtime

- Imports: `numpy`, `scipy`, `math`, `statistics`, `qdash_metrics` (public names only). No
  other modules, no relative imports, no other scripts.
- Disabled builtins: `open`, `exec`, `eval`, `compile`, `input`, `breakpoint`, `help`,
  `exit`, `quit`; `__import__` is checked.
- Scripts run in the deployment's `metric-runner` container as a per-run user, with no network,
  database or API access: the data broker in the API process is the only data path, scoped to
  the caller's project and the evaluated chip.
- Limits (deployment defaults): 60 s wall clock (`METRIC_SCRIPT_TIMEOUT_SECONDS`), 1024 MiB
  of extra address space (`METRIC_SCRIPT_MEMORY_MB`), two concurrent runs across the whole
  deployment with a global queue (`METRIC_RUNNER_CONCURRENCY`), 8 MiB protocol output,
  16 KiB of `print` log, 256 KiB of source. Broker caps: 5,000 records per `history()` call,
  2,000 data requests per evaluation, 400-day history span.

### Failures

- **Per-cell error**: the cell has `status: "error"`, a message and a diagnostic with the
  script line and function. A broker cap reached for one target also lands here, naming the
  cap. The other cells are valid.
- **Whole-run failure** (HTTP 422, `detail = {message, diagnostics, log}`): the script does
  not compile or violates the import policy, the metric ID or a parameter is invalid, the
  legend is invalid, a series metric has no, too many or invalid targets (or a scalar metric
  has targets), the series points exceed 8,192 in total, or the worker hit the timeout, memory
  or output limit.
- **HTTP 429**: the evaluation queue is full (all worker slots busy for 5 s, or too many runs
  waiting). Retry later.
- **HTTP 503**: the metric script runner is unavailable or stopped mid-run; there is no result
  and a save recorded nothing. Retry later or ask an administrator to check the
  `metric-runner` service; do not change the script.
- **HTTP 409** on save: `expected_revision` no longer matches, or another save landed while this
  one was validating (every save is a compare-and-set on the stored revision); read the script
  again before saving. On evaluation: the chip has no usable topology.

Validation (`qdash_validate_metric_script`, and every save) runs the module body and registers
the metrics without reading data, so errors inside metric functions show up only when they
are evaluated.
