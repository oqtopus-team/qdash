# Metric script templates

QDash ships four starter scripts. Read one with `qdash_query` `metric_script_template`
(`templateId`); a new script created from a template is a copy, so later template changes do
not affect it.

## `getting_started`

Three small qubit metrics that show the main parts of the API:

- `coherence_ratio` (T2 echo / T1, dimensionless): two `latest()` values divided as
  Quantities.
- `upper_frequency_gap` (MHz): the frequency difference to the qubit one row up, found with
  `ctx.topology.offset(target, row=-1)`; returns `None` on the top row.
- `mean_dispersive_shift` (MHz): the mean of `history()` over the period, as a `CellResult`
  with `label` and `count`.

No parameters. Use it to learn the shape of a script or as the base for simple per-qubit
ratios and differences.

## `zx90_median`

One pair metric, `zx90_median` ("Median ZX90 gate fidelity", unit `%`, `hops=(1,)`):

- Reads `ctx.data["zx90_gate_fidelity"][pair].history()` for the directed coupling over the
  period. Excluded results are skipped; there is no reverse-direction fallback, so `0>1` and
  `1>0` are separate cells with their own observations.
- Takes the median of the raw observations (`statistics.median`), converted to percent.
- Returns `CellResult(median, assessment={"label": "median of n", "count": n, "checks":
  [samples, min, max, latest timestamp]})`.
- With fewer than `min_samples` observations it returns `CellResult(None, color="#737373",
  assessment={"label": "fewer than min_samples observations", "count": n, ...})`, so the cell
  is shown as missing with the reason and the count.
- Parameter `min_samples` (integer, default 3, min 1).
- Continuous legend: 90 % red, 97 % amber, 99 % blue.

It is the pattern for any "statistic of a metric over a period per coupling" request: swap
the catalog metric, the statistic, the unit and the legend. For a qubit metric, set
`target="qubit"` (drop `hops`) and index with the qubit ID.

Walkthrough of the user story "median ZX90 gate fidelity over the last 14 days per
coupling": preview `zx90_median` with `period {"kind": "relative", "days": 14}` on the user's
chip, report how many couplings have a value and how many are missing for lack of samples,
then save the script and add a `metric_script` panel (`view: "map"` or `"table"`,
`direction: "both"`, `hops: [1]`) pinned to the saved active revision.

## `zx90_daily_trend`

One series pair metric, `zx90_daily_trend` ("ZX90 gate fidelity trend", unit `%`, `hops=(1,)`,
`result="series"`), for "daily or weekly median ZX90 over a period" requests:

- Reads `ctx.data["zx90_gate_fidelity"][pair].history()` once per selected directed pair over
  the period; excluded results are skipped and there is no reverse-direction fallback.
- Splits the period with `time_bins(ctx.start, ctx.end, interval)`: UTC days, or ISO weeks
  starting Monday 00:00 UTC. The first and last bins are clipped to the period and their
  reason says `partial bin`.
- Each point is the median of the bin's raw observations in percent (a fidelity stored as
  0.99 `a.u.` is 99 %), with `count`, `start` and `end`. A bin without observations is a
  `no_data` gap; one with fewer than `min_samples` valid observations is an `insufficient` gap,
  including a bin whose observations all fall outside the valid range (reason such as
  `0 of 2 observations valid; 2 outside 0-100 % left out`). Nothing is interpolated.
- Observations outside `[min_valid, max_valid]` % (default 0 to 100, the physical range of a
  fidelity) are left out of the median and counted in the point's reason and in the
  `outside valid range` check; stored results are not changed. A record stored with unit
  `%` and value 99 is read as catalog value x scale, 9,900 %, by the `history()` unit rules,
  so it is left out and counted rather than silently included.
- Parameters: `interval` (`day` or `week`, default `day`), `min_samples` (integer, default
  1), `min_valid` and `max_valid` (percent).

Walkthrough of "ZX90 daily median trend of 0>1 and 1>0 over the last 4 weeks": preview with
`targets ["0>1", "1>0"]` and `period {"kind": "relative", "days": 28}`, report the points,
gaps and `n=1` points per pair, then propose a `metric_script` panel with `view:
"timeseries"`, the same `targets`, `params {"interval": "day"}` (or `"week"`) and `hops: [1]`,
pinned to the script's active revision. Do not select every coupling of the chip.

## `collision`

Qubex-compatible frequency collision checks, adapted from qdash-playground. Thirteen metrics,
one per check: `Type0A` (qubit quality, a qubit metric) and the pair checks `Type0B`,
`Type1A`, `Type1B`, `Type1C`, `Type2A`, `Type2B`, `Type2C`, `Type3A`, `Type3B`, `Type7`,
`Type8`, `Type9`. The pair checks declare `hops=(1, 2)`, but only `Type1A` and `Type3A` are
evaluated at distance 2, and only within a MUX; the others return `None` (empty) there.

- Inputs are the latest values within the period (frequencies, anharmonicities, T1, T2,
  coupling strengths). A stored zero counts as missing. Missing coupling strength, T1 or T2
  falls back to the default parameters, and the fallback is listed in the cell's
  `estimates`.
- Each cell's value is the worst ratio of a term to its limit (dimensionless), coloured blue
  below 1, amber at 1 and red above, with every term in `checks` and the verdict as the
  `label`. `Type2C` is different: its value is the signed two-photon detuning in MHz, red
  inside the `two_photon_window`, amber at its edge and blue outside. When an input is
  missing or a formula is undefined, the cell is missing (grey) with the reason in its label.
- Parameters: frequency bounds, maximum detuning, minimum T1/T2, the adiabatic and CR control
  limits, the CNOT time and the fallback values; `Type2C` has only `two_photon_window`.
- `Type2B` keeps qubex's division formula; `Type2C` is a static screening, not a leakage
  rate.

The `frequency-collision-map` dashboard template uses this script: creating a dashboard from
it reuses the project's shared collision script (or creates one) and pins its panels to that
script's active revision.
