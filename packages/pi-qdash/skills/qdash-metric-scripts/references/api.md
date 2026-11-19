# The `qdash_metrics` API

Metric scripts import from `qdash_metrics` only. The module exports `metric`, `CellResult`,
`Legend`, `Parameter`, `MissingData`, `Measurement`, `Quantity`, `QubitPair`, `units` and
`unit_name`.

## `@metric`

```python
from qdash_metrics import metric

@metric(title="T2 echo / T1", unit="dimensionless")
def coherence_ratio(target, ctx):
    return ctx.data["t2_echo"][target].latest() / ctx.data["t1"][target].latest()
```

`@metric(title, unit, target="qubit", hops=(1, 2), parameters=None, legend=None)`

| Argument | Meaning |
| --- | --- |
| `title` | Display name; must not be empty. |
| `unit` | Declared output unit, a pint unit name. `%`, `μs`, `""` and `a.u.` are accepted and normalized (`percent`, `us`, `dimensionless`, `au`). Use `dimensionless` for ratios. An unknown unit fails validation. |
| `target` | `"qubit"` (default) or `"pair"`. |
| `hops` | Pair metrics only: the pair distances the metric is meaningful for, a non-empty subset of `(1, 2)`. `hops=(1,)` evaluates coupled pairs only. |
| `parameters` | `{name: Parameter(...)}`; read the effective values from `ctx.params`. |
| `legend` | A `Legend`, or a function `legend(ctx) -> Legend` (for legends that depend on parameters). |

The function name is the metric's ID (`metric_id` in previews and panels). Renaming the
function makes it a different metric; panels that used the old name stop validating. Helper
functions without the decorator are fine. One script may define several metrics.

The function is called as `function(target, ctx)` once per target:

- Qubit metrics: `target` is a normalized qubit ID string (`"5"`), once for every qubit of the
  chip topology.
- Pair metrics: `target` is a `QubitPair(source, target, hops)`, once for **each direction** of
  every pair whose coupling-graph distance is in `hops`, over the whole chip. `0>1` and `1>0`
  are separate cells.

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
  or before end.

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
- Scripts run in the deployment's `agent-exec` container as a per-run user, with no network,
  database or API access: the data broker in the API process is the only data path, scoped to
  the caller's project and the evaluated chip.
- Limits (deployment defaults): 60 s wall clock (`METRIC_SCRIPT_TIMEOUT_SECONDS`), 1024 MiB
  of extra address space (`METRIC_SCRIPT_MEMORY_MB`), two concurrent runs across the whole
  deployment with a global queue (`AGENT_EXEC_METRIC_CONCURRENCY`), 8 MiB protocol output,
  16 KiB of `print` log, 256 KiB of source. Broker caps: 5,000 records per `history()` call,
  2,000 data requests per evaluation, 400-day history span.

### Failures

- **Per-cell error**: the cell has `status: "error"`, a message and a diagnostic with the
  script line and function. A broker cap reached for one target also lands here, naming the
  cap. The other cells are valid.
- **Whole-run failure** (HTTP 422, `detail = {message, diagnostics, log}`): the script does
  not compile or violates the import policy, the metric ID or a parameter is invalid, the
  legend is invalid, or the worker hit the timeout, memory or output limit.
- **HTTP 429**: the evaluation queue is full (all worker slots busy for 5 s, or too many runs
  waiting). Retry later.
- **HTTP 503**: the metric script runner is unavailable; nothing ran and a save recorded
  nothing. Retry later or ask an administrator to check the `agent-exec` service; do not
  change the script.
- **HTTP 409** on save: `expected_revision` no longer matches; on evaluation: the chip has no
  usable topology.

Validation (`qdash_validate_metric_script`, and every save) runs the module body and registers
the metrics without reading data, so errors inside metric functions show up only when they
are evaluated.
