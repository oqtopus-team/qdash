"""Getting started: three small metrics that show the main parts of the API.

Adapted from qdash-playground examples/analysis.py (Apache License 2.0).

- ``ctx.data[metric][qubit].latest()`` returns the latest value within the panel period
  as a pint Quantity with the catalog unit and scale applied.
- ``ctx.topology`` gives qubit positions and neighbours.
- ``.history()`` returns every observation within the period, oldest first.
"""

import statistics

from qdash_metrics import CellResult, metric


@metric(title="T2 echo / T1", unit="dimensionless")
def coherence_ratio(target, ctx):
    return ctx.data["t2_echo"][target].latest() / ctx.data["t1"][target].latest()


@metric(title="Upper neighbour frequency gap", unit="MHz")
def upper_frequency_gap(target, ctx):
    other = ctx.topology.offset(target, row=-1)
    if other is None:
        return None
    frequency = ctx.data["qubit_frequency"]
    return abs(frequency[target].latest() - frequency[other].latest())


@metric(title="Mean dispersive shift", unit="MHz")
def mean_dispersive_shift(target, ctx):
    history = ctx.data["dispersive_shift"][target].history()
    if not history:
        return None
    values = [point.value.to("MHz").magnitude for point in history]
    return CellResult(
        statistics.fmean(values),
        assessment={"label": f"mean of {len(values)}", "count": len(values)},
    )
