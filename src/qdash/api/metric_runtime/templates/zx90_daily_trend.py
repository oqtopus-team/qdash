"""Daily or weekly median ZX90 gate fidelity of the selected directed couplings.

Each point is the median of the raw ZX90 interleaved randomized benchmarking observations
whose task started in one UTC time bin; excluded results are skipped. Days start at 00:00 UTC
and weeks on Monday 00:00 UTC. The first and last bins are clipped to the panel period and
marked partial. A bin without enough observations is a gap, not an interpolated value.

history() converts every observation to percent first: a raw fidelity stored as 0.99 a.u. is
99 %. Observations outside [min_valid, max_valid] % are left out of the median and counted in
the point's reason; the stored results are not changed. The default range is the physical
range of a fidelity, 0 to 100 %. A bin whose observations all fall outside the range is
"insufficient" (0 valid, with the number observed and left out), not "no_data".
"""

import statistics

from qdash_metrics import Parameter, SeriesPoint, SeriesResult, metric, time_bins


@metric(
    title="ZX90 gate fidelity trend",
    unit="%",
    target="pair",
    hops=(1,),
    result="series",
    parameters={
        "interval": Parameter(default="day", choices=["day", "week"], label="Time bin (UTC)"),
        "min_samples": Parameter(default=1, min=1, step=1, label="Minimum observations per bin"),
        "min_valid": Parameter(default=0.0, min=0, max=100, unit="%", label="Lowest valid value"),
        "max_valid": Parameter(
            default=100.0, min=0, max=100, unit="%", label="Highest valid value"
        ),
    },
)
def zx90_daily_trend(pair, ctx):
    low, high = ctx.params["min_valid"], ctx.params["max_valid"]
    if low > high:
        raise ValueError("min_valid must not exceed max_valid")
    # Directed: the coupling "source-target" only, no reverse-direction fallback.
    history = ctx.data["zx90_gate_fidelity"][pair].history()
    points = []
    out_of_range = 0
    for time_bin in time_bins(ctx.start, ctx.end, ctx.params["interval"]):
        observed = [m.value.to("percent").magnitude for m in time_bin.select(history)]
        values = [value for value in observed if low <= value <= high]
        excluded = len(observed) - len(values)
        out_of_range += excluded
        notes = []
        if excluded:
            notes.append(f"{excluded} outside {low:g}-{high:g} % left out")
        if time_bin.partial:
            notes.append("partial bin")
        count = len(values)
        if not observed:
            value, status = None, "no_data"
            notes.insert(0, "no observations")
        elif count == 0:
            # Observed, but every observation fell outside the valid range.
            value, status = None, "insufficient"
            notes.insert(0, f"0 of {len(observed)} observations valid")
        elif count < ctx.params["min_samples"]:
            value, status = None, "insufficient"
            notes.insert(0, f"{count} < min_samples {ctx.params['min_samples']}")
        else:
            value, status = statistics.median(values), "ok"
        points.append(
            SeriesPoint(
                time_bin.start,
                value,
                count=count,
                status=status,
                reason="; ".join(notes) or None,
                start=time_bin.start,
                end=time_bin.end,
            )
        )
    return SeriesResult(
        points,
        label="daily median" if ctx.params["interval"] == "day" else "weekly median",
        assessment={
            "count": len(history),
            "checks": [
                ("observations", len(history)),
                ("outside valid range", out_of_range),
            ],
        },
    )
