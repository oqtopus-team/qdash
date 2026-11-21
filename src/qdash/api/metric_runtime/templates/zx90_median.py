"""Median ZX90 gate fidelity per directed coupling over the panel period.

Every ZX90 interleaved randomized benchmarking result in the period is one observation;
excluded results are skipped. The median of the raw observations is shown together with the
number of observations, so a value backed by one measurement is easy to tell apart from a
value backed by many.
"""

import statistics

from qdash_metrics import CellResult, Legend, Parameter, metric

NOT_ENOUGH = "#737373"


@metric(
    title="Median ZX90 gate fidelity",
    unit="%",
    target="pair",
    hops=(1,),
    parameters={
        "min_samples": Parameter(default=3, min=1, step=1, label="Minimum observations"),
    },
    legend=Legend.continuous([(90, "#dc2626"), (97, "#d97706"), (99, "#2563eb")]),
)
def zx90_median(pair, ctx):
    # Directed: the coupling "source-target" only, no reverse-direction fallback.
    history = ctx.data["zx90_gate_fidelity"][pair].history()
    values = [point.value.to("percent").magnitude for point in history]
    count = len(values)
    if count < ctx.params["min_samples"]:
        return CellResult(
            None,
            color=NOT_ENOUGH,
            assessment={
                "label": "fewer than min_samples observations",
                "count": count,
                "checks": [("samples", count), ("min_samples", ctx.params["min_samples"])],
            },
        )
    median = statistics.median(values)
    return CellResult(
        median,
        assessment={
            "label": f"median of {count}",
            "count": count,
            "checks": [
                ("samples", count),
                ("min (%)", min(values)),
                ("max (%)", max(values)),
                ("latest", history[-1].timestamp.isoformat()),
            ],
        },
    )
